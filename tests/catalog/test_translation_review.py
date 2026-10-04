from __future__ import annotations

import json

import pytest

from almonium_book_processor.catalog.ai_translation import (
    SUBSCRIPTION_TIER,
    create_parallel_translation,
    run_translation_inline,
)
from almonium_book_processor.catalog.fidelity_audit import audit_context
from almonium_book_processor.catalog.models import PipelineRun, TextQualityFinding
from almonium_book_processor.catalog.translation_review import merge, review_translation
from tests.catalog.test_ai_translation import canonical_edition, output_line, translated

pytestmark = pytest.mark.django_db

TRANSLATION = "Похмурої листопадової ночі я побачив завершення своїх трудів і зрадів."


def issue(quote, correction, *, kind="meaning", severity="material", reviewer="codex"):
    return {
        "block_id": "c1.p2",
        "source_quote": "accomplishment of my toils",
        "adapted_quote": quote,
        "kind": kind,
        "severity": severity,
        "explanation": "why",
        "suggested_correction": correction,
        "quote_verified": True,
        "reviewer": reviewer,
    }


class FakeReviewer:
    """Answers the three steps by the schema name of the request: review, opinion, wording."""

    def __init__(self, issues, *, agrees=True, better="", wording="", verdict="keep", fix=""):
        self.issues = issues
        self.verdict = verdict
        self.fix = fix
        self.agrees = agrees
        self.better = better
        self.wording = wording
        self.bodies = []

    def respond(self, body):
        self.bodies.append(body)
        step = body["text"]["format"]["name"]
        asked = json.loads(body["input"]).get("findings", [])
        if step == "second_opinion":
            payload = {
                "verdicts": [
                    {
                        "id": f["id"],
                        "real_error": self.agrees,
                        "reason": "second look",
                        "better_correction": self.better,
                    }
                    for f in asked
                ]
            }
        elif step == "adjudication":
            payload = {
                "rulings": [
                    {"id": f["id"], "verdict": self.verdict, "reason": "ruled", "new_fix": self.fix}
                    for f in asked
                ]
            }
        elif step == "final_wording":
            payload = {
                "replacements": [{"id": f["id"], "replacement": self.wording} for f in asked]
            }
        else:
            payload = {
                "issues": [
                    {k: v for k, v in i.items() if k not in ("quote_verified", "reviewer")}
                    for i in self.issues
                ],
                "assessment": "ok",
            }
        return {
            "output": [
                {
                    "type": "message",
                    "content": [
                        {"type": "output_text", "text": json.dumps(payload, ensure_ascii=False)}
                    ],
                }
            ],
            "usage": {"input_tokens": 100, "output_tokens": 50},
        }


def translated_edition(tier=SUBSCRIPTION_TIER):
    source = canonical_edition()
    edition = create_parallel_translation(
        source_edition=source,
        target_language="uk",
        register="period-faithful",
        tier=tier,
    )

    class Translator:
        name = "claude-code"

        def respond(self, body):
            line = output_line(
                "chapter-1",
                [translated("c1.h1", "Розділ I"), translated("c1.p2", TRANSLATION)],
            )
            return line["response"]["body"]

    run_translation_inline(str(edition.id), tier=tier, provider=Translator())
    edition.refresh_from_db()
    return edition


def test_merge_ranks_by_agreement_and_never_rejects():
    texts = {"c1.p2": TRANSLATION}
    merged = merge(
        {
            "claude-code": [
                issue("завершення своїх трудів", "здійснення своїх трудів", reviewer="claude-code"),
                issue("зрадів", "утішився", kind="style", severity="minor", reviewer="claude-code"),
            ],
            "codex": [
                issue("побачив завершення", "узрів завершення"),
                issue("Похмурої", "Понурої", kind="style", severity="minor"),
            ],
        },
        texts,
        author="claude-code",
    )

    by_quote = {m["adapted_quote"]: m for m in merged}
    assert len(merged) == 3
    both = by_quote["побачив завершення"]
    assert both["evidence"]["agreement"] == "both"
    assert both["evidence"]["reviewers"] == ["codex", "claude-code"]
    # the outside reviewer's wording is proposed; the translator's own is kept beside it
    assert both["suggested_correction"] == "узрів завершення"
    assert both["evidence"]["alternative_correction"] == "здійснення своїх трудів"
    assert by_quote["Похмурої"]["evidence"]["agreement"] == "outside"
    assert by_quote["зрадів"]["evidence"]["agreement"] == "author"
    # ranked: both, then the outside reviewer alone, then the translator's model alone
    assert [m["evidence"]["agreement"] for m in merged] == ["both", "outside", "author"]


def test_review_cross_checks_and_queues_every_finding():
    edition = translated_edition()
    # the translator's model disputes what the outside reviewer raised; the outside reviewer
    # confirms what the translator's model raised
    opus = FakeReviewer([issue("зрадів", "утішився", kind="style", severity="minor")], agrees=False)
    outside = FakeReviewer([issue("завершення своїх трудів", "здійснення своїх трудів")])

    run = review_translation(
        str(edition.id),
        providers={
            "claude-code": opus,
            "codex": outside,
            "adjudicator": FakeReviewer([], verdict="apply_proposed"),
        },
    )

    assert run.status == PipelineRun.Status.SUCCEEDED
    assert run.summary["review"]["agreement"] == {"both": 0, "confirmed": 1, "disputed": 1}
    findings = {f.evidence["agreement"]: f for f in edition.text_quality_findings.all()}
    confirmed, disputed = findings["confirmed"], findings["disputed"]
    assert confirmed.evidence["agreement"] == "confirmed"
    # findings are labelled with the models that raised and judged them
    assert confirmed.evidence["reviewers"] == ["opus"]
    assert confirmed.evidence["second_opinion"]["by"] == "gpt-6.1-sol"
    # a "no" from the other reviewer lowers the rank and keeps the reason; nothing is dropped
    assert disputed.status == TextQualityFinding.Status.OPEN
    assert disputed.original_text == "завершення своїх трудів"
    assert disputed.suggested_text == "здійснення своїх трудів"
    assert disputed.evidence["agreement"] == "disputed"
    assert disputed.evidence["second_opinion"] == {"by": "opus", "reason": "second look"}
    # the adjudicator ruled on the disputed finding and on the style one
    assert disputed.evidence["adjudication"]["verdict"] == "apply_proposed"
    assert confirmed.evidence["adjudication"]["verdict"] == "apply_proposed"
    # both reviewers saw the source and the translation, in the edition's languages
    assert "Ukrainian" in outside.bodies[0]["instructions"]
    assert json.loads(opus.bodies[0]["input"])["blocks"][1]["adapted"] == TRANSLATION


def test_the_translator_writes_the_final_wording_from_every_candidate():
    edition = translated_edition()
    opus = FakeReviewer([], wording="звершення своїх трудів")
    outside = FakeReviewer([issue("завершення своїх трудів", "здійснення своїх трудів")])
    opus.better = "досягнення своїх трудів"

    review_translation(
        str(edition.id),
        providers={"claude-code": opus, "codex": outside, "adjudicator": FakeReviewer([])},
    )

    finding = edition.text_quality_findings.get()
    # the translator's wording is what is queued; what the editors proposed is kept beside it
    assert finding.suggested_text == "звершення своїх трудів"
    assert finding.evidence["candidates"] == ["здійснення своїх трудів", "досягнення своїх трудів"]
    assert finding.evidence["final_wording_by"] == "opus"
    asked = json.loads(opus.bodies[-1]["input"])["findings"][0]
    assert asked["span_to_replace"] == "завершення своїх трудів"


def test_an_empty_final_wording_keeps_the_reviewers_correction():
    edition = translated_edition()
    opus = FakeReviewer([], wording="")
    outside = FakeReviewer([issue("завершення своїх трудів", "здійснення своїх трудів")])

    review_translation(
        str(edition.id),
        providers={"claude-code": opus, "codex": outside, "adjudicator": FakeReviewer([])},
    )

    assert edition.text_quality_findings.get().suggested_text == "здійснення своїх трудів"


def disputed_edition(adjudicator):
    """An outside finding the translator's model disputes, then ruled on."""

    edition = translated_edition()
    review_translation(
        str(edition.id),
        providers={
            "claude-code": FakeReviewer([], agrees=False),
            "codex": FakeReviewer([issue("завершення своїх трудів", "здійснення своїх трудів")]),
            "adjudicator": adjudicator,
        },
    )
    return edition.text_quality_findings.get()


def test_a_keep_ruling_strips_the_replacement_so_bulk_apply_cannot_push_it_through():
    finding = disputed_edition(FakeReviewer([], verdict="keep"))

    assert finding.status == TextQualityFinding.Status.OPEN
    assert finding.suggested_text == ""
    assert finding.code == "fidelity_uncertain"
    assert finding.evidence["adjudication"]["verdict"] == "keep"
    assert finding.evidence["proposed_before_ruling"] == "здійснення своїх трудів"


def test_a_new_fix_ruling_replaces_the_proposal():
    finding = disputed_edition(FakeReviewer([], verdict="new_fix", fix="звершення своїх трудів"))

    assert finding.suggested_text == "звершення своїх трудів"
    assert finding.code == "fidelity_material"
    assert finding.evidence["proposed_before_ruling"] == "здійснення своїх трудів"


def test_a_new_fix_ruling_without_a_fix_goes_to_a_person():
    finding = disputed_edition(FakeReviewer([], verdict="new_fix", fix=""))

    assert finding.evidence["adjudication"]["verdict"] == "human_review"
    assert finding.code == "fidelity_uncertain"
    assert finding.suggested_text == "здійснення своїх трудів"


@pytest.mark.django_db(transaction=True)
def test_windows_read_in_parallel_record_the_same_findings():
    edition = translated_edition()
    outside = FakeReviewer([issue("побачив завершення", "узрів завершення")])
    opus = FakeReviewer([issue("побачив завершення", "уздрів завершення", reviewer="claude-code")])

    run = review_translation(
        str(edition.id),
        providers={"claude-code": opus, "codex": outside, "adjudicator": FakeReviewer([])},
        workers=2,
    )

    assert run.status == PipelineRun.Status.SUCCEEDED
    finding = TextQualityFinding.objects.get(edition=edition)
    assert finding.evidence["agreement"] == "both"


def test_the_outside_reviewer_reads_at_the_effort_its_seat_names(settings):
    settings.TRANSLATION_OUTSIDE_REVIEWER = "codex:gpt-6.1-sol:medium"
    edition = translated_edition()
    outside, opus = FakeReviewer([]), FakeReviewer([])

    review_translation(
        str(edition.id),
        providers={"claude-code": opus, "codex": outside, "adjudicator": FakeReviewer([])},
    )

    assert outside.bodies[0]["reasoning"] == {"effort": "medium"}
    assert opus.bodies[0]["reasoning"] == {"effort": "high"}


def test_a_block_is_sent_once_however_many_findings_it_has():
    edition = translated_edition()
    outside = FakeReviewer(
        [
            issue("побачив завершення", "узрів завершення"),
            issue("Похмурої", "Понурої", kind="style", severity="minor"),
        ]
    )
    opus = FakeReviewer([])

    review_translation(
        str(edition.id),
        providers={"claude-code": opus, "codex": outside, "adjudicator": FakeReviewer([])},
    )

    # the second opinion on two findings in one paragraph carries that paragraph once
    asked = json.loads(opus.bodies[-1]["input"])
    assert list(asked["blocks"]) == ["c1.p2"]
    assert asked["blocks"]["c1.p2"]["translated"] == TRANSLATION
    assert [f["block_id"] for f in asked["findings"]] == ["c1.p2", "c1.p2"]
    assert all("translated" not in f and "source" not in f for f in asked["findings"])
    assert "given once under blocks" in opus.bodies[-1]["instructions"]


def test_the_adjudicator_is_never_the_model_that_translated(settings):
    from almonium_book_processor.catalog.translation_review import _adjudicator

    settings.TRANSLATION_ADJUDICATORS = "codex:gpt-6-astra, claude-code:fable"

    assert _adjudicator("opus") == {
        "name": "adjudicator",
        "provider": "codex",
        "model": "gpt-6-astra",
        "effort": "high",
    }
    assert _adjudicator("gpt-6-astra")["model"] == "fable"


def test_a_gpt_translation_gets_its_final_wording_from_the_model_that_wrote_it(settings):
    from almonium_book_processor.catalog.ai_translation import CODEX_TIER

    settings.CODEX_TRANSLATION_MODEL = "gpt-6-astra"
    edition = translated_edition(tier=CODEX_TIER)
    outside = FakeReviewer(
        [issue("побачив завершення", "узрів завершення")], wording="узрів звершення"
    )
    opus = FakeReviewer([])

    review_translation(
        str(edition.id),
        providers={"claude-code": opus, "codex": outside, "adjudicator": FakeReviewer([])},
    )

    finding = TextQualityFinding.objects.get(edition=edition)
    # the Codex reviewer's seat runs another model than the translator; the wording is the
    # translator's, and the request for it names that model
    assert finding.evidence["final_wording_by"] == "gpt-6-astra"
    wording = next(b for b in outside.bodies if "settling the final wording" in b["instructions"])
    assert wording["model"] == "gpt-6-astra"
    assert finding.evidence["reviewers"] == ["gpt-6.1-sol"]


def test_agreed_meaning_findings_skip_the_adjudicator():
    edition = translated_edition()
    adjudicator = FakeReviewer([], verdict="keep")
    review_translation(
        str(edition.id),
        providers={
            "claude-code": FakeReviewer([]),
            "codex": FakeReviewer([issue("завершення своїх трудів", "здійснення своїх трудів")]),
            "adjudicator": adjudicator,
        },
    )

    finding = edition.text_quality_findings.get()
    # confirmed by the other editor and a matter of meaning: no ruling asked, proposal stands
    assert adjudicator.bodies == []
    assert "adjudication" not in finding.evidence
    assert finding.suggested_text == "здійснення своїх трудів"


def test_a_reviewed_translation_shows_its_findings_in_the_audit_panel():
    edition = translated_edition()
    review_translation(
        str(edition.id),
        providers={
            "claude-code": FakeReviewer([]),
            "codex": FakeReviewer([issue("завершення своїх трудів", "здійснення своїх трудів")]),
            "adjudicator": FakeReviewer([]),
        },
    )

    context = audit_context(edition)

    assert context["fidelity_audit_state"] == "current"
    assert [f.suggested_text for f in context["fidelity_findings"]] == ["здійснення своїх трудів"]
    assert context["fidelity_counts"]["material"] == 1
    assert context["fidelity_applicable"] == 1
    # the review needs the CLI's login, so the panel offers no button to queue it
    assert context["fidelity_audit_enabled"] is False


def test_review_refuses_an_edition_that_is_not_a_machine_translation():
    with pytest.raises(ValueError, match="machine translation"):
        review_translation(str(canonical_edition().id))
