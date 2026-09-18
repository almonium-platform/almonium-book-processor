"""The adaptation floor: probes, the fidelity audit, and what the work records from them."""

import json
import uuid
from types import SimpleNamespace

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from almonium_book_processor.catalog.adaptation import queue_pilot, run_pilot
from almonium_book_processor.catalog.adaptation_floor import (
    PROBE_VERSION,
    judge_standalone_pilot,
    ladder,
    probe_sample,
    queue_probe,
    reached_levels,
    refresh_adaptation_floor,
    run_probe,
)
from almonium_book_processor.catalog.book_adaptation import queue_book, run_book
from almonium_book_processor.catalog.fidelity_audit import (
    AUDIT_VERSION,
    FINDING_CODE,
    audit_context,
    audit_pilot,
    queue_edition_audit,
    run_edition_audit,
)
from almonium_book_processor.catalog.models import (
    AIRun,
    Chapter,
    ContentBlock,
    Edition,
    PipelineRun,
    Work,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def source(settings, monkeypatch):
    settings.OPENAI_API_KEY = "fake"
    settings.OPENAI_TRANSLATION_QUALITY_MODEL = "test-quality"
    settings.OPENAI_TRANSLATION_DRAFT_MODEL = "test-draft"
    for task in (
        "adapt_chapter_pilot",
        "run_floor_probe",
        "audit_edition_fidelity",
        "adapt_book",
        "enrich_adapted_book",
        "analyze_edition_chapters",
        "project_chapter_analysis",
    ):
        monkeypatch.setattr(f"almonium_book_processor.catalog.tasks.{task}.delay", lambda _: None)
    work = Work.objects.create(slug="floor", title="Frankenstein", author="Shelley")
    edition = Edition.objects.create(
        work=work,
        slug="floor-en",
        title="Frankenstein",
        author="Shelley",
        language="en",
        cefr_level="C1",
        status="ready",
        source_sha256="a" * 64,
    )
    for seq in (1, 2, 3, 4):
        chapter = Chapter.objects.create(edition=edition, sequence=seq, title=f"Chapter {seq}")
        for index, (kind, text) in enumerate(
            [
                ("heading", f"Chapter {seq}"),
                ("paragraph", "Ere dawn, he departed."),
                ("paragraph", "He was afraid."),
            ]
        ):
            ContentBlock.objects.create(
                edition=edition,
                chapter=chapter,
                sequence=index,
                block_id=f"c{seq}.b{index}",
                block_type=kind,
                text=text,
                align_group=uuid.uuid4(),
            )
    return edition


def _response(payload: dict, cost_tokens=(100, 50)) -> dict:
    return {
        "id": "resp",
        "status": "completed",
        "usage": {"input_tokens": cost_tokens[0], "output_tokens": cost_tokens[1]},
        "output": [
            {"type": "message", "content": [{"type": "output_text", "text": json.dumps(payload)}]}
        ],
    }


class Generator:
    """Adapts the second block of every chapter the way the pilot tests expect."""

    def __init__(self):
        self.calls = 0

    def respond(self, body):
        self.calls += 1
        blocks = [
            {"block_id": b["block_id"], "text": b["text"], "decision": "kept", "reason": ""}
            for b in json.loads(body["input"])["blocks"]
        ]
        for block in blocks:
            if block["text"] == "Ere dawn, he departed.":
                block.update(text="Before dawn, he left.", decision="adapted", reason="Simpler.")
        return _response({"blocks": blocks, "review_notes": []})


class Judge:
    def __init__(self, level="B2"):
        self.level = level
        self.calls = 0

    def respond(self, body):
        self.calls += 1
        data = json.loads(body["input"])
        assert "target_level" not in data and "author" not in data
        return _response(
            {
                "cefr_estimate": self.level,
                "confidence": 0.7,
                "archaism_score": 0.0,
                "modernisation_would_help": False,
                "evidence": [
                    {
                        "block_id": next(
                            b["block_id"] for b in data["blocks"] if "Before" in b["text"]
                        ),
                        "quote": "Before dawn",
                        "dimension": "syntax",
                        "explanation": "Direct narration.",
                    }
                ],
                "spoiler_free_description": "A traveler sets out before sunrise.",
                "recap": "He leaves.",
                "hard_words": [],
                "themes": [],
                "characters": [],
                "setting": "",
                "content_flags": [],
            }
        )


class Auditor:
    def __init__(self, issues=None):
        self.issues = issues or []
        self.calls = 0
        self.inputs = []

    def respond(self, body):
        self.calls += 1
        data = json.loads(body["input"])
        self.inputs.append(data)
        present = {pair["block_id"] for pair in data["blocks"]}
        issues = [issue for issue in self.issues if issue["block_id"] in present]
        return _response({"issues": issues, "assessment": "Read every pair."})


MATERIAL = {
    "block_id": "c1.b1",
    # The model wraps quotes in quotation marks and curly apostrophes; the book does not.
    "source_quote": "\u201cEre dawn,\u201d",
    "adapted_quote": '"Before dawn"',
    "severity": "material",
    "explanation": "The departure lost its urgency.",
    "suggested_correction": "Before dawn, he had already left.",
}
MINOR = {**MATERIAL, "block_id": "c2.b1", "severity": "minor", "adapted_quote": "not in text"}


def _pilot(source, level="B2", chapter=None):
    chapter = chapter or source.chapters.first()
    run = queue_pilot(source.id, chapter.id, target_level=level, dispatch=False)
    run_pilot(run.id, provider=Generator())
    run.refresh_from_db()
    return run


def test_pilot_audit_verifies_quotes_caches_and_records_on_the_pilot(source):
    pilot = _pilot(source)
    auditor = Auditor([MATERIAL, MINOR])
    review = audit_pilot(pilot.id, provider=auditor)
    assert review["counts"] == {"material": 1, "minor": 0, "uncertain": 0}
    assert review["issues"][0]["quote_verified"] is True
    assert review["blocks"] == 3
    assert auditor.inputs[0]["blocks"][1] == {
        "block_id": "c1.b1",
        "source": "Ere dawn, he departed.",
        "adapted": "Before dawn, he left.",
    }
    assert audit_pilot(pilot.id, provider=auditor) == review
    assert auditor.calls == 1
    pilot.refresh_from_db()
    assert pilot.summary["fidelity_audit"]["counts"]["material"] == 1
    audit = PipelineRun.objects.get(processor_version=AUDIT_VERSION)
    assert audit.summary["pilot_id"] == str(pilot.id) and audit.status == "succeeded"
    ai = AIRun.objects.get(pk=review["ai_run_ids"][0])
    assert ai.pipeline_run_id == audit.id and ai.estimated_cost_usd > 0
    assert ai.prompt_template.name == "literary-fidelity-editor"
    source.blocks.filter(block_id="c1.b2").update(text="Changed.")
    with pytest.raises(ValueError, match="source changed"):
        audit_pilot(pilot.id, provider=auditor)


def test_a_standalone_pilot_is_judged_and_audited_after_generation_but_book_chunks_are_not(
    source,
):
    pilot = _pilot(source)
    judge, auditor = Judge("B2"), Auditor()
    judge_standalone_pilot(pilot.id, judge=judge, auditor=auditor)
    pilot.refresh_from_db()
    assert pilot.summary["difficulty_check"]["max_level"] == "B2"
    assert pilot.summary["fidelity_audit"]["counts"]["material"] == 0
    book = queue_book(source.id)
    run_book(book.id, provider=Generator())
    chunk = book.edition.pipeline_runs.filter(processor_version="b2-chapter-pilot-v1").first()
    judge_standalone_pilot(chunk.id, judge=judge, auditor=auditor)
    chunk.refresh_from_db()
    assert "difficulty_check" not in chunk.summary and "fidelity_audit" not in chunk.summary
    assert judge.calls == 1 and auditor.calls == 1


def test_probe_samples_first_middle_and_last_substantive_chapters(source):
    Chapter.objects.filter(edition=source, sequence=1).update(analysis_role="front")
    assert [c.sequence for c in probe_sample(source)] == [2, 3, 4]
    Chapter.objects.filter(edition=source).update(analysis_role="front")
    assert [c.sequence for c in probe_sample(source)] == [1, 3, 4]


def test_probe_passes_when_the_judge_is_at_target_and_the_audit_is_clean(source):
    with pytest.raises(ValueError, match="Reach the level above first"):
        queue_probe(source.id, "B1")
    run = queue_probe(source.id, "B2")
    assert queue_probe(source.id, "B2").id == run.id
    assert [c["sequence"] for c in run.summary["chapters"]] == [1, 3, 4]
    generator, judge = Generator(), Judge("B2")
    auditor = Auditor([{**MINOR, "block_id": "c3.b1"}])
    run_probe(run.id, provider=generator, judge=judge, auditor=auditor)
    run.refresh_from_db()
    assert run.status == "succeeded" and run.summary["verdict"] == "passed"
    assert generator.calls == judge.calls == auditor.calls == 3
    assert [r["judge_max_level"] for r in run.summary["results"]] == ["B2", "B2", "B2"]
    assert run.summary["results"][1]["minor"] == 1
    source.work.refresh_from_db()
    assert source.work.adapts_to is None
    assert source.work.adaptation_evidence["levels"]["B2"]["state"] == "probe_passed"
    rows = ladder(source)
    assert [(r["level"], r["state"]) for r in rows] == [("B2", "probe_passed"), ("B1", "untried")]
    assert rows[0]["can_generate"] and not rows[0]["can_probe"]
    assert rows[1]["can_probe"]
    # Running the probe again reuses every paid result.
    run.status = "queued"
    run.save()
    run_probe(run.id, provider=generator, judge=judge, auditor=auditor)
    assert generator.calls == judge.calls == auditor.calls == 3


@pytest.mark.parametrize("problem", ["above_target", "material"])
def test_a_failed_probe_closes_the_ladder(source, problem):
    run = queue_probe(source.id, "B2")
    judge = Judge("C1" if problem == "above_target" else "B2")
    auditor = Auditor([MATERIAL] if problem == "material" else [])
    run_probe(run.id, provider=Generator(), judge=judge, auditor=auditor)
    run.refresh_from_db()
    assert run.summary["verdict"] == "failed"
    assert run.summary["reasons"] == (
        ["Chapter 1 judged C1", "Chapter 3 judged C1", "Chapter 4 judged C1"]
        if problem == "above_target"
        else ["Chapter 1: 1 material fidelity finding(s)"]
    )
    rows = ladder(source)
    assert rows[0]["state"] == "probe_failed" and not rows[0]["can_probe"]
    assert rows[1]["state"] == "untried" and not rows[1]["can_probe"]
    with pytest.raises(ValueError, match="Reach the level above first"):
        queue_probe(source.id, "B1")
    with pytest.raises(ValueError, match="B2:"):
        queue_probe(source.id, "B2")
    source.work.refresh_from_db()
    evidence = source.work.adaptation_evidence["levels"]["B2"]
    assert evidence["state"] == "probe_failed" and evidence["probe_id"] == str(run.id)
    assert len(evidence["pilot_ids"]) == 3


def test_a_probe_under_a_superseded_configuration_can_be_run_again(source, settings):
    run = queue_probe(source.id, "B2")
    run_probe(run.id, provider=Generator(), judge=Judge("C1"), auditor=Auditor())
    assert ladder(source)[0]["state"] == "probe_failed"
    settings.OPENAI_TRANSLATION_QUALITY_MODEL = "next-quality"
    rows = ladder(source)
    assert rows[0]["state"] == "untried" and rows[0]["can_probe"]
    assert "superseded" in rows[0]["note"]
    assert queue_probe(source.id, "B2").id != run.id


def test_an_erroring_probe_records_the_reason_and_can_be_retried(source):
    run = queue_probe(source.id, "B2")

    class Broken:
        def respond(self, body):
            return {"status": "incomplete", "usage": {}, "output": []}

    with pytest.raises(ValueError):
        run_probe(run.id, provider=Broken(), judge=Judge(), auditor=Auditor())
    run.refresh_from_db()
    assert run.status == "failed" and "Chapter 1: generation failed" in run.error
    rows = ladder(source)
    assert rows[0]["state"] == "error" and rows[0]["can_probe"]
    assert queue_probe(source.id, "B2").id == run.id
    run_probe(run.id, provider=Generator(), judge=Judge(), auditor=Auditor())
    run.refresh_from_db()
    assert run.summary["verdict"] == "passed"


@pytest.fixture
def adaptation(source):
    book = queue_book(source.id)
    run_book(book.id, provider=Generator())
    return Edition.objects.get(pk=book.edition_id)


def test_edition_audit_turns_material_findings_into_review_items(adaptation):
    assert audit_context(adaptation)["fidelity_audit_state"] == "none"
    run = queue_edition_audit(adaptation.id)
    assert run.summary["chapters"] == 4 and run.summary["windows"] == 4
    auditor = Auditor([MATERIAL, MINOR])
    run_edition_audit(run.id, provider=auditor)
    run.refresh_from_db()
    assert run.status == "succeeded" and auditor.calls == 4
    assert run.summary["review"]["counts"] == {"material": 1, "minor": 1, "uncertain": 0}
    finding = adaptation.warnings.get(code=FINDING_CODE, resolved_at=None)
    assert finding.block.block_id == "c1.b1" and finding.pipeline_run_id == run.id
    assert "lost its urgency" in finding.message and "Suggested:" in finding.message
    context = audit_context(adaptation)
    assert context["fidelity_audit_state"] == "current"
    assert context["fidelity_open_findings"] == 1
    assert [i["block_id"] for i in context["fidelity_secondary_findings"]] == ["c2.b1"]
    assert context["fidelity_secondary_findings"][0]["quote_verified"] is False
    # Same text, same audit: nothing is paid twice and the item is not duplicated.
    assert queue_edition_audit(adaptation.id).id == run.id
    run_edition_audit(run.id, provider=auditor)
    assert auditor.calls == 4
    assert adaptation.warnings.filter(code=FINDING_CODE).count() == 1
    # A text change makes the audit stale; the next audit re-reads only that chapter
    # and supersedes the old finding.
    adaptation.blocks.filter(block_id="c1.b1").update(text="Before dawn, he had already left.")
    assert audit_context(adaptation)["fidelity_audit_state"] == "stale"
    again = queue_edition_audit(adaptation.id)
    assert again.id != run.id
    run_edition_audit(again.id, provider=auditor)
    assert auditor.calls == 5
    finding.refresh_from_db()
    assert finding.resolved_at is not None
    replacement = adaptation.warnings.get(code=FINDING_CODE, resolved_at=None)
    assert replacement.pipeline_run_id == again.id and replacement.id != finding.id


def test_edition_audit_needs_block_for_block_lineage(source):
    standalone = Edition.objects.create(
        work=source.work,
        slug="floor-en-other",
        language="en",
        edition_type="adaptation",
        source_edition=source,
    )
    chapter = Chapter.objects.create(edition=standalone, sequence=1)
    ContentBlock.objects.create(
        edition=standalone, chapter=chapter, sequence=1, block_id="x", text="Text."
    )
    with pytest.raises(ValueError, match="no source block"):
        queue_edition_audit(standalone.id)
    with pytest.raises(ValueError, match="Only an adaptation"):
        queue_edition_audit(source.id)


@pytest.fixture
def passing_difficulty(monkeypatch):
    """The difficulty gate is proven elsewhere; here it passes for every adaptation."""

    analysis_run = SimpleNamespace(id=uuid.uuid4())
    monkeypatch.setattr(
        "almonium_book_processor.catalog.adaptation_floor.analysis_context",
        lambda edition: {"chapter_analysis_run": analysis_run, "book_difficulty": None},
    )
    monkeypatch.setattr(
        "almonium_book_processor.catalog.adaptation_floor.adaptation_quality",
        lambda edition, analysis=None: {"adaptation_target": "B2", "adaptation_blocker": ""},
    )
    return analysis_run


def test_the_floor_is_recorded_only_from_editions_that_pass_both_gates(
    adaptation, passing_difficulty, monkeypatch
):
    from almonium_book_processor.catalog.publication import publish_to_almonium
    from almonium_book_processor.catalog.services import resolve_review_warning

    work = adaptation.work
    refresh_adaptation_floor(work)
    work.refresh_from_db()
    assert work.adapts_to is None and work.adaptation_evidence == {}
    run = queue_edition_audit(adaptation.id)
    run_edition_audit(run.id, provider=Auditor([MATERIAL]))
    work.refresh_from_db()
    assert work.adapts_to is None  # an open material finding is not "clean"
    reviewer = get_user_model().objects.create_user("editor", is_staff=True)
    finding = adaptation.warnings.get(code=FINDING_CODE)
    resolve_review_warning(edition=adaptation, warning_id=finding.id, reviewer=reviewer)
    work.refresh_from_db()
    assert work.adapts_to == "B2"
    record = work.adaptation_evidence["levels"]["B2"]
    assert record["state"] == "reached" and record["edition_slug"] == adaptation.slug
    assert record["fidelity_run_id"] == str(run.id)
    assert record["difficulty_run_id"] == str(passing_difficulty.id)
    assert reached_levels(work) == ["B2"]
    rows = ladder(adaptation.source_edition)
    assert rows[0]["state"] == "reached" and rows[1]["can_probe"]

    sent = {}
    monkeypatch.setattr(
        "almonium_book_processor.catalog.publication._signed_post",
        lambda path, payload, failure: sent.update(payload) or {"bookId": "b"},
    )
    publish_to_almonium(adaptation)
    assert sent["adaptsTo"] == "B2" and sent["reachedLevels"] == ["B2"]

    # A text change makes the audit stale, and the level is no longer reached.
    adaptation.blocks.filter(block_id="c1.b1").update(text="Changed again.")
    refresh_adaptation_floor(work)
    work.refresh_from_db()
    assert work.adapts_to is None
    assert "B2" not in work.adaptation_evidence["levels"]


def test_a_promoted_work_keeps_the_floor_it_arrived_with(adaptation, passing_difficulty):
    work = adaptation.work
    Work.objects.filter(pk=work.pk).update(
        adapts_to="B1", adaptation_evidence={"levels": {"B1": {"state": "reached"}}}
    )
    Edition.objects.filter(pk=adaptation.pk).update(promoted_from="staging")
    refresh_adaptation_floor(work)
    work.refresh_from_db()
    assert work.adapts_to == "B1"


def test_the_bundle_carries_the_floor():
    from almonium_book_processor.catalog.promotion import BUNDLE_SCHEMA_VERSION, WORK_FIELDS

    assert "adapts_to" in WORK_FIELDS and "adaptation_evidence" in WORK_FIELDS
    assert BUNDLE_SCHEMA_VERSION >= 4


def test_the_pages_offer_the_next_probe_and_the_audit(client, source):
    client.force_login(get_user_model().objects.create_user("staff", is_staff=True))
    page = client.get(reverse("catalog:edition-detail", args=[source.id])).content.decode()
    assert 'id="adaptation-ladder"' in page
    assert "Probe B2 (3 chapters, paid)" in page
    assert "Probe B1" not in page and "Reach the level above first" in page
    response = client.post(
        reverse("catalog:queue-floor-probe", args=[source.id]), {"target_level": "B2"}
    )
    assert response.status_code == 302
    assert source.pipeline_runs.filter(processor_version=PROBE_VERSION, status="queued").exists()
    page = client.get(reverse("catalog:edition-detail", args=[source.id])).content.decode()
    assert "Probing" in page and "Probe B2 (3 chapters, paid)" not in page

    book = queue_book(source.id)
    run_book(book.id, provider=Generator())
    adaptation = Edition.objects.get(pk=book.edition_id)
    page = client.get(reverse("catalog:edition-detail", args=[adaptation.id])).content.decode()
    assert 'id="fidelity-audit"' in page and "Audit fidelity (paid)" in page
    assert "adaptation-ladder" not in page
    response = client.post(reverse("catalog:queue-fidelity-audit", args=[adaptation.id]))
    assert response.status_code == 302
    assert adaptation.pipeline_runs.filter(processor_version=AUDIT_VERSION).exists()
    page = client.get(reverse("catalog:edition-detail", args=[adaptation.id])).content.decode()
    assert "Audit fidelity (paid)" not in page and "Running" in page

    pilot = _pilot(source)
    judge_standalone_pilot(pilot.id, judge=Judge(), auditor=Auditor([MATERIAL]))
    page = client.get(
        reverse("catalog:adaptation-pilot", args=[source.id, pilot.id])
    ).content.decode()
    assert "Fidelity audit: 1 material" in page and "lost its urgency" in page


def test_a_probe_can_be_backfilled_from_pilots_judged_and_audited_by_scripts(source):
    from almonium_book_processor.catalog.adaptation_floor import backfill_probe

    with pytest.raises(ValueError, match="No B1 pilot"):
        backfill_probe(source, "B1")
    chapters = list(source.chapters.order_by("sequence"))
    pilots = [_pilot(source, "B1", chapter) for chapter in chapters[:2]]
    judge_standalone_pilot(pilots[0].id, judge=Judge("B2"), auditor=Auditor())
    # The second pilot was judged, and audited by a script that wrote its own ledger row.
    from almonium_book_processor.catalog.pilot_difficulty import assess_pilot

    assess_pilot(pilots[1].id, provider=Judge("B1"))
    with pytest.raises(ValueError, match="never audited"):
        backfill_probe(source, "B1")
    audit_pilot(pilots[1].id, provider=Auditor([{**MATERIAL, "block_id": "c2.b1"}]))
    PipelineRun.objects.filter(pk=pilots[1].id).update(
        summary={**PipelineRun.objects.get(pk=pilots[1].id).summary, "fidelity_audit": None}
    )
    run = backfill_probe(source, "B1")
    assert run.summary["backfilled"] and run.summary["verdict"] == "failed"
    assert run.summary["reasons"] == [
        "Chapter 1 judged B2",
        "Chapter 2: 1 material fidelity finding(s)",
    ]
    assert backfill_probe(source, "B1").id == run.id
    rows = ladder(source)
    assert rows[1]["state"] == "probe_failed"
    source.work.refresh_from_db()
    assert source.work.adaptation_evidence["levels"]["B1"]["state"] == "probe_failed"
