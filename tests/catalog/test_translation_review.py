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


def issue(quote, correction, *, kind="meaning", severity="material", reviewer="openai"):
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
    def __init__(self, issues):
        self.issues = issues
        self.bodies = []

    def respond(self, body):
        self.bodies.append(body)
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


def translated_edition():
    source = canonical_edition()
    edition = create_parallel_translation(
        source_edition=source,
        target_language="uk",
        register="period-faithful",
        tier=SUBSCRIPTION_TIER,
    )

    class Translator:
        name = "claude-code"

        def respond(self, body):
            line = output_line(
                "chapter-1",
                [translated("c1.h1", "Розділ I"), translated("c1.p2", TRANSLATION)],
            )
            return line["response"]["body"]

    run_translation_inline(str(edition.id), tier=SUBSCRIPTION_TIER, provider=Translator())
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
            "openai": [
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
    assert both["evidence"]["reviewers"] == ["openai", "claude-code"]
    # the outside reviewer's wording is proposed; the translator's own is kept beside it
    assert both["suggested_correction"] == "узрів завершення"
    assert both["evidence"]["alternative_correction"] == "здійснення своїх трудів"
    assert by_quote["Похмурої"]["evidence"]["agreement"] == "outside"
    assert by_quote["зрадів"]["evidence"]["agreement"] == "author"
    # ranked: both, then the outside reviewer alone, then the translator's model alone
    assert [m["evidence"]["agreement"] for m in merged] == ["both", "outside", "author"]


def test_review_queues_every_finding_in_the_fidelity_queue():
    edition = translated_edition()
    opus = FakeReviewer([issue("зрадів", "утішився", kind="style", severity="minor")])
    outside = FakeReviewer([issue("завершення своїх трудів", "здійснення своїх трудів")])

    run = review_translation(str(edition.id), providers={"claude-code": opus, "openai": outside})

    assert run.status == PipelineRun.Status.SUCCEEDED
    assert run.summary["review"]["agreement"] == {"both": 0, "outside": 1, "author": 1}
    findings = list(edition.text_quality_findings.order_by("-confidence"))
    assert [f.code for f in findings] == ["fidelity_material", "fidelity_minor"]
    material = findings[0]
    assert material.status == TextQualityFinding.Status.OPEN
    assert material.original_text == "завершення своїх трудів"
    assert material.suggested_text == "здійснення своїх трудів"
    assert material.evidence["kind"] == "meaning"
    assert material.evidence["agreement"] == "outside"
    # a single reviewer's style finding is queued too, lower down, not dropped
    assert findings[1].evidence == {**findings[1].evidence, "kind": "style", "agreement": "author"}
    # both reviewers saw the source and the translation, in the edition's languages
    assert "Ukrainian" in outside.bodies[0]["instructions"]
    assert json.loads(opus.bodies[0]["input"])["blocks"][1]["adapted"] == TRANSLATION


def test_a_reviewed_translation_shows_its_findings_in_the_audit_panel():
    edition = translated_edition()
    review_translation(
        str(edition.id),
        providers={
            "claude-code": FakeReviewer([]),
            "openai": FakeReviewer([issue("завершення своїх трудів", "здійснення своїх трудів")]),
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
