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
    # the Claude reviewer disputes what the outside reviewer raised; the outside reviewer
    # confirms what the Claude reviewer raised
    opus = FakeReviewer([issue("зрадів", "утішився")], agrees=False)
    outside = FakeReviewer([issue("завершення своїх трудів", "здійснення своїх трудів")])

    run = review_translation(str(edition.id), providers={"claude-code": opus, "codex": outside})

    assert run.status == PipelineRun.Status.SUCCEEDED
    assert run.summary["review"]["agreement"] == {"both": 0, "confirmed": 1, "disputed": 1}
    findings = {f.evidence["agreement"]: f for f in edition.text_quality_findings.all()}
    confirmed, disputed = findings["confirmed"], findings["disputed"]
    # findings are labelled with the models that raised and judged them
    assert confirmed.evidence["reviewers"] == ["claude-opus-5-5"]
    assert confirmed.evidence["second_opinion"]["by"] == "gpt-6.1-sol"
    assert confirmed.suggested_text == "утішився" and confirmed.code == "fidelity_material"
    # A "no" from the other reviewer keeps the finding and the reason, and takes the
    # replacement away: what one model alone believes cannot be applied with a click.
    assert disputed.status == TextQualityFinding.Status.OPEN
    assert disputed.original_text == "завершення своїх трудів"
    assert disputed.suggested_text == "" and disputed.code == "fidelity_uncertain"
    assert disputed.evidence["proposed_first"] == "здійснення своїх трудів"
    assert disputed.evidence["second_opinion"] == {"by": "claude-opus-5-5", "reason": "second look"}
    # nobody rules on it and nobody rewrites it: two readings and two second opinions
    assert len(opus.bodies) == 2 and len(outside.bodies) == 2
    # both reviewers saw the source and the translation, in the edition's languages
    assert "Ukrainian" in outside.bodies[0]["instructions"]
    assert json.loads(opus.bodies[0]["input"])["blocks"][1]["adapted"] == TRANSLATION


def test_a_better_correction_from_the_confirming_editor_is_the_one_queued():
    edition = translated_edition()
    opus = FakeReviewer([], better="досягнення своїх трудів")
    outside = FakeReviewer([issue("завершення своїх трудів", "здійснення своїх трудів")])

    review_translation(str(edition.id), providers={"claude-code": opus, "codex": outside})

    finding = edition.text_quality_findings.get()
    assert finding.suggested_text == "досягнення своїх трудів"
    assert finding.evidence["proposed_first"] == "здійснення своїх трудів"
    assert finding.evidence["agreement"] == "confirmed"


def test_the_editors_are_asked_only_for_what_misleads_or_stops_a_reader():
    edition = translated_edition()
    opus, outside = FakeReviewer([]), FakeReviewer([])

    review_translation(str(edition.id), providers={"claude-code": opus, "codex": outside})

    asked = outside.bodies[0]["instructions"]
    assert "Report only what would mislead or stop a reader" in asked
    assert "Do not report minor points" in asked


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
