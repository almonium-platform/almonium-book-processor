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
        "refresh_edition_after_revision",
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
    "source_quote": "\u201cEre dawn, he departed.\u201d",
    "adapted_quote": '"Before dawn, he left."',
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


def test_edition_audit_turns_every_finding_into_an_applicable_item(adaptation):
    assert audit_context(adaptation)["fidelity_audit_state"] == "none"
    run = queue_edition_audit(adaptation.id)
    assert run.summary["chapters"] == 4 and run.summary["windows"] == 4
    auditor = Auditor([MATERIAL, MINOR])
    run_edition_audit(run.id, provider=auditor)
    run.refresh_from_db()
    assert run.status == "succeeded" and auditor.calls == 4
    assert run.summary["review"]["counts"] == {"material": 1, "minor": 1, "uncertain": 0}
    material = adaptation.text_quality_findings.get(code="fidelity_material")
    assert material.status == "open" and material.block.block_id == "c1.b1"
    assert (material.start_offset, material.end_offset) == (0, len("Before dawn, he left."))
    assert material.original_text == "Before dawn, he left."
    assert material.suggested_text == "Before dawn, he had already left."
    assert material.can_apply and material.evidence["source_quote"] == "Ere dawn, he departed."
    minor = adaptation.text_quality_findings.get(code="fidelity_minor")
    assert minor.block.block_id == "c2.b1" and not minor.can_apply and minor.suggested_text == ""
    context = audit_context(adaptation)
    assert context["fidelity_audit_state"] == "current"
    assert context["fidelity_open_findings"] == 1 and context["fidelity_applicable"] == 1
    assert context["fidelity_counts"] == {"material": 1, "minor": 1, "uncertain": 0}
    # Same text, same audit: nothing is paid twice and nothing is duplicated.
    assert queue_edition_audit(adaptation.id).id == run.id
    run_edition_audit(run.id, provider=auditor)
    assert auditor.calls == 4
    assert adaptation.text_quality_findings.filter(code__startswith="fidelity_").count() == 2
    # A text change makes the audit stale; the next audit re-reads only that chapter
    # and supersedes the old findings.
    adaptation.blocks.filter(block_id="c1.b1").update(text="Before dawn, he had already left.")
    assert audit_context(adaptation)["fidelity_audit_state"] == "stale"
    again = queue_edition_audit(adaptation.id)
    assert again.id != run.id
    run_edition_audit(again.id, provider=auditor)
    assert auditor.calls == 5
    material.refresh_from_db()
    assert material.status == "superseded"
    replacement = adaptation.text_quality_findings.get(code="fidelity_material", status="open")
    assert replacement.pipeline_run_id == again.id and not replacement.can_apply


def test_fidelity_suggestions_are_applied_in_bulk_as_audited_revisions(
    adaptation, django_capture_on_commit_callbacks
):
    from almonium_book_processor.catalog.services import (
        apply_fidelity_findings,
        dismiss_fidelity_findings,
    )

    reviewer = get_user_model().objects.create_user("editor", is_staff=True)
    run = queue_edition_audit(adaptation.id)
    second = {
        **MATERIAL,
        "block_id": "c1.b2",
        "source_quote": "afraid",
        "adapted_quote": "afraid",
        "severity": "minor",
        "suggested_correction": "terrified",
    }
    auditor = Auditor([MATERIAL, second, MINOR])
    run_edition_audit(run.id, provider=auditor)
    with pytest.raises(ValueError, match="no fidelity suggestion"):
        apply_fidelity_findings(edition=adaptation, reviewer=reviewer, severities=["uncertain"])
    with django_capture_on_commit_callbacks(execute=True):
        assert (
            apply_fidelity_findings(
                edition=adaptation, reviewer=reviewer, severities=["material", "minor"]
            )
            == 2
        )
    assert adaptation.blocks.get(block_id="c1.b1").text == "Before dawn, he had already left."
    assert adaptation.blocks.get(block_id="c1.b2").text == "He was terrified."
    assert adaptation.block_revisions.count() == 2
    assert "Applied fidelity audit suggestions" in adaptation.block_revisions.first().notes
    assert set(
        adaptation.text_quality_findings.filter(code__startswith="fidelity_").values_list(
            "status", flat=True
        )
    ) == {"applied", "open"}
    # The auditor's own wording went in verbatim, so its verdict carries to the new
    # text: no re-read is queued, the run is re-keyed and says what it was carried over.
    assert (
        not adaptation.pipeline_runs.filter(processor_version=AUDIT_VERSION)
        .exclude(pk=run.pk)
        .exists()
    )
    context = audit_context(adaptation)
    assert context["fidelity_audit_state"] == "current" and context["fidelity_carried"] == 2
    run.refresh_from_db()
    assert {c["block_id"] for c in run.summary["carried"]} == {"c1.b1", "c1.b2"}
    # The difficulty judge never saw the new wording, so its analysis is queued.
    assert adaptation.pipeline_runs.filter(stage="chapter_analysis", status="queued").exists()
    # The remaining finding is still open on its (unchanged) block.
    assert adaptation.text_quality_findings.get(status="open").block.block_id == "c2.b1"
    assert (
        dismiss_fidelity_findings(edition=adaptation, reviewer=reviewer, severities=["minor"]) == 1
    )
    assert not adaptation.text_quality_findings.filter(status="open").exists()
    # The carried windows follow the run: after a hand edit elsewhere, a re-read pays
    # for that chapter alone, not for the chapters the auditor's own words changed,
    # and the dismissal the editor already made stands.
    adaptation.blocks.filter(block_id="c4.b2").update(text="He was, by hand, afraid.")
    again = queue_edition_audit(adaptation.id)
    calls_before = auditor.calls
    run_edition_audit(again.id, provider=auditor)
    assert auditor.calls == calls_before + 1
    assert not adaptation.text_quality_findings.filter(status="open").exists()
    context = audit_context(adaptation)
    assert context["fidelity_audit_state"] == "current"
    assert [f.stable_block_id for f in context["fidelity_dismissed"]] == ["c2.b1"]


def test_a_price_or_budget_change_does_not_repay_audited_windows(adaptation, monkeypatch):
    auditor = Auditor()
    run = queue_edition_audit(adaptation.id)
    run_edition_audit(run.id, provider=auditor)
    assert auditor.calls == 4
    monkeypatch.setattr("almonium_book_processor.catalog.fidelity_audit.MAX_OUTPUT_TOKENS", 99_000)
    monkeypatch.setattr(
        "almonium_book_processor.catalog.fidelity_audit.TRANSLATION_MODEL_PRICING",
        {"quality": {"input": "9", "cached_input": "9", "output": "9"}, "draft": {}},
    )
    again = queue_edition_audit(adaptation.id)
    assert again.id == run.id  # same identity, same run
    run.status = "queued"
    run.save()
    run_edition_audit(run.id, provider=auditor)
    assert auditor.calls == 4


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
    from almonium_book_processor.catalog.services import dismiss_text_quality_finding

    work = adaptation.work
    refresh_adaptation_floor(work)
    work.refresh_from_db()
    assert work.adapts_to is None and work.adaptation_evidence == {}
    run = queue_edition_audit(adaptation.id)
    run_edition_audit(run.id, provider=Auditor([MATERIAL]))
    work.refresh_from_db()
    assert work.adapts_to is None  # an open material finding is not "clean"
    reviewer = get_user_model().objects.create_user("editor", is_staff=True)
    finding = adaptation.text_quality_findings.get(code="fidelity_material")
    dismiss_text_quality_finding(edition=adaptation, finding_id=finding.id, reviewer=reviewer)
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
    audit = adaptation.pipeline_runs.get(processor_version=AUDIT_VERSION)
    page = client.get(reverse("catalog:edition-detail", args=[adaptation.id])).content.decode()
    assert "Audit fidelity (paid)" not in page and "Running" in page
    audit.status = "queued"
    audit.save()
    run_edition_audit(audit.id, provider=Auditor([MATERIAL, MINOR]))
    page = client.get(reverse("catalog:edition-detail", args=[adaptation.id])).content.decode()
    assert "Apply all 1 suggestions" in page and "Dismiss all 2 open findings" in page
    assert (
        "lost its urgency" in page and "Source-text QA" not in page.split('id="fidelity-audit"')[0]
    )
    response = client.post(
        reverse("catalog:apply-fidelity-findings", args=[adaptation.id]),
        {"severity": ["material"], "confirm": "1"},
    )
    assert response.status_code == 302
    assert adaptation.blocks.get(block_id="c1.b1").text == "Before dawn, he had already left."
    response = client.post(reverse("catalog:dismiss-fidelity-findings", args=[adaptation.id]), {})
    assert response.status_code == 302
    assert adaptation.text_quality_findings.filter(status="open").count() == 1
    client.post(
        reverse("catalog:dismiss-fidelity-findings", args=[adaptation.id]), {"confirm": "1"}
    )
    assert not adaptation.text_quality_findings.filter(status="open").exists()

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


def test_excerpts_mark_the_sentence_around_the_quote():
    from almonium_book_processor.catalog.fidelity_audit import excerpt
    from almonium_book_processor.catalog.templatetags.catalog_extras import mark_excerpt

    text = "First sentence. Ere dawn, he departed. He was afraid! Last one."
    assert excerpt(text, "“he departed”") == ("Ere dawn, ", "he departed", ".")
    assert excerpt(text, "afraid") == ("He was ", "afraid", "!")
    assert excerpt(text, "not there") == (text, "", "")
    assert excerpt(text, "\u201cFirst ... he departed\u201d")[1] == "he departed"
    long = "word " * 200
    assert excerpt(long, "nope")[0].endswith(" …") and len(excerpt(long, "nope")[0]) < 320
    at = text.index("afraid")
    assert excerpt(text, "afraid", whole=True) == (text[:at], "afraid", text[at + 6 :])
    assert mark_excerpt(text, "afraid") == "He was <mark>afraid</mark>!"
    assert mark_excerpt("a < b", "nope") == "a &lt; b"


def test_a_dismissal_can_be_reopened_and_an_unplaceable_finding_closed_by_hand(adaptation):
    from almonium_book_processor.catalog.services import (
        apply_finding_with_block_text,
        dismiss_text_quality_finding,
        reopen_text_quality_finding,
    )

    reviewer = get_user_model().objects.create_user("editor", is_staff=True)
    run = queue_edition_audit(adaptation.id)
    run_edition_audit(run.id, provider=Auditor([MATERIAL, MINOR]))
    material = adaptation.text_quality_findings.get(code="fidelity_material")
    dismiss_text_quality_finding(edition=adaptation, finding_id=material.id, reviewer=reviewer)
    context = audit_context(adaptation)
    assert [f.id for f in context["fidelity_dismissed"]] == [material.id]
    assert context["fidelity_findings"][0].source_text == "Ere dawn, he departed."
    assert context["fidelity_manual"] == 1  # the minor finding's quote is not in the text
    reopen_text_quality_finding(edition=adaptation, finding_id=material.id, reviewer=reviewer)
    material.refresh_from_db()
    assert material.status == "open"
    with pytest.raises(ValueError, match="Only a dismissed"):
        reopen_text_quality_finding(edition=adaptation, finding_id=material.id, reviewer=reviewer)
    minor = adaptation.text_quality_findings.get(code="fidelity_minor")
    assert not minor.can_apply
    apply_finding_with_block_text(
        edition=adaptation,
        finding_id=minor.id,
        revised_text="He was terrified.",
        reviewer=reviewer,
        notes="Kept the stronger word.",
    )
    minor.refresh_from_db()
    assert minor.status == "applied"
    assert adaptation.blocks.get(block_id="c2.b1").text == "He was terrified."
    assert adaptation.block_revisions.get().notes == "Kept the stronger word."


def test_the_change_preview_shows_what_the_sentence_becomes():
    from almonium_book_processor.catalog.fidelity_audit import change_preview
    from almonium_book_processor.catalog.templatetags.catalog_extras import (
        change_preview as tag,
    )

    text = "Before dawn, he left. He was afraid."
    segments, placed = change_preview(text, '"he left"', "he had already left")
    assert placed
    assert "".join(s["text"] for s in segments if s["op"] != "delete") == (
        "Before dawn, he had already left."
    )
    assert [s["op"] for s in segments] == ["equal", "delete", "insert", "equal"]
    html = tag(text, "he left", "he had already left")
    assert html == "Before dawn, <del>he left</del><ins>he had already left</ins>."
    segments, placed = change_preview(text, "not there ... at all", "He was terrified.")
    assert not placed and any(s["op"] == "delete" for s in segments)


def test_a_hand_edit_leaves_the_audit_stale_and_prices_the_re_read(
    adaptation, django_capture_on_commit_callbacks
):
    from almonium_book_processor.catalog.services import apply_text_quality_finding

    reviewer = get_user_model().objects.create_user("editor", is_staff=True)
    run = queue_edition_audit(adaptation.id)
    run_edition_audit(run.id, provider=Auditor([MATERIAL, MINOR]))
    material = adaptation.text_quality_findings.get(code="fidelity_material")
    with django_capture_on_commit_callbacks(execute=True):
        apply_text_quality_finding(
            edition=adaptation,
            finding_id=material.id,
            replacement="Before dawn he was gone.",  # not the auditor's words
            reviewer=reviewer,
        )
    context = audit_context(adaptation)
    assert context["fidelity_audit_state"] == "stale"
    assert context["fidelity_stale_chapters"] == 1
    assert context["fidelity_stale_cost"] == "0.00"  # the fake provider is free
    assert context["fidelity_carried"] == 0
    assert (
        not adaptation.pipeline_runs.filter(processor_version=AUDIT_VERSION)
        .exclude(pk=run.pk)
        .exists()
    )


def test_applying_one_finding_keeps_its_neighbour_on_the_block_placeable(adaptation):
    from almonium_book_processor.catalog.services import apply_fidelity_findings

    reviewer = get_user_model().objects.create_user("editor", is_staff=True)
    run = queue_edition_audit(adaptation.id)
    neighbour = {
        **MATERIAL,
        "source_quote": "departed",
        "adapted_quote": "left",
        "severity": "minor",
        "suggested_correction": "set off",
    }
    run_edition_audit(run.id, provider=Auditor([MATERIAL, neighbour]))
    apply_fidelity_findings(edition=adaptation, reviewer=reviewer, severities=["material"])
    assert adaptation.blocks.get(block_id="c1.b1").text == "Before dawn, he had already left."
    minor = adaptation.text_quality_findings.get(code="fidelity_minor")
    assert minor.status == "open" and minor.can_apply
    text = adaptation.blocks.get(block_id="c1.b1").text
    assert text[minor.start_offset : minor.end_offset] == "left"
    assert audit_context(adaptation)["fidelity_audit_state"] == "current"


def test_a_phrase_level_fix_carries_the_difficulty_verdict_forward(
    adaptation, django_capture_on_commit_callbacks
):
    from almonium_book_processor.catalog.chapter_analysis import (
        analysis_context,
        analyze_chapters,
        queue_analysis,
    )
    from almonium_book_processor.catalog.services import apply_fidelity_findings, revise_block_text

    reviewer = get_user_model().objects.create_user("editor", is_staff=True)
    # A real chapter is paragraphs long; one corrected phrase is a sliver of it.
    filler = " ".join(f"Sentence number {i} keeps the chapter long." for i in range(40))
    for edition in (adaptation.source_edition, adaptation):
        chapter = edition.chapters.get(sequence=1)
        ContentBlock.objects.create(
            edition=edition,
            chapter=chapter,
            sequence=9,
            block_id="c1.b9",
            block_type="paragraph",
            text=filler,
            align_group=uuid.uuid4(),
        )
    analysis = queue_analysis(str(adaptation.id))
    judge = Judge("B2")
    analyze_chapters(str(analysis.id), provider=judge)
    assert analysis_context(adaptation)["projection_state"] == "complete"
    judged_calls = judge.calls
    audit = queue_edition_audit(adaptation.id)
    run_edition_audit(audit.id, provider=Auditor([MATERIAL]))
    with django_capture_on_commit_callbacks(execute=True):
        apply_fidelity_findings(edition=adaptation, reviewer=reviewer, severities=["material"])
    # One phrase changed: the verdict is carried, nothing is queued, nothing is paid.
    context = analysis_context(adaptation)
    assert context["projection_state"] == "complete"
    assert (
        not adaptation.pipeline_runs.filter(stage="chapter_analysis")
        .exclude(pk=analysis.pk)
        .exists()
    )
    analysis.refresh_from_db()
    assert analysis.summary["carried"][0]["change"] < 0.02
    assert judge.calls == judged_calls
    # A rewrite of the block is more than a phrase: a real analysis is queued.
    with django_capture_on_commit_callbacks(execute=True):
        revise_block_text(
            edition=adaptation,
            block_id=adaptation.blocks.get(block_id="c2.b1").id,
            revised_text=" ".join(["word"] * 60),
            editor=reviewer,
        )
        from almonium_book_processor.catalog.services import _requeue_analysis_after_commit

        _requeue_analysis_after_commit(adaptation)
    assert adaptation.pipeline_runs.filter(stage="chapter_analysis", status="queued").exists()


def test_both_sides_show_the_sentences_that_hold_any_quoted_words():
    from almonium_book_processor.catalog.fidelity_audit import side_excerpt

    source = (
        "Earlier words. You cannot contest the benefit I shall confer "
        "by finding the passage. Later."
    )
    adapted = (
        "Earlier words. You cannot deny the benefit I shall confer. I may find the passage. Later."
    )
    source_quote = "“the benefit I shall confer ... by finding the passage”"
    adapted_quote = "I may find the passage"
    # The adaptation split the sentence: the adapted side shows both halves, its own quote marked.
    segments = side_excerpt(adapted, adapted_quote, source_quote)
    assert "".join(s["text"] for s in segments) == (
        "You cannot deny the benefit I shall confer. I may find the passage."
    )
    assert [s["text"] for s in segments if s["marked"]] == ["I may find the passage"]
    # The source side marks each fragment of its ellipsis quote.
    segments = side_excerpt(source, source_quote, adapted_quote)
    assert [s["text"] for s in segments if s["marked"]] == [
        "the benefit I shall confer",
        "by finding the passage",
    ]
    assert "".join(s["text"] for s in segments).startswith("You cannot contest")
    assert side_excerpt("word " * 100, "nothing here", "")[0]["text"].endswith(" …")


def test_a_correction_written_for_the_whole_clause_replaces_the_whole_clause():
    from almonium_book_processor.catalog.fidelity_audit import replacement_span

    text = "At night the southern winds blow us quickly towards those shores, and we sleep."
    start, end = text.index("the southern winds"), text.index("the southern winds") + 18
    span = replacement_span(text, start, end, "the strong southern winds blow us quickly")
    assert text[span[0] : span[1]] == "the southern winds blow us quickly"
    text = (
        "Nor should any conclusion be drawn from the following pages that favours any "
        "philosophical doctrine of whatever kind; and the opinions are the author's."
    )
    quote = "that favours any philosophical doctrine of whatever kind"
    start = text.index(quote)
    span = replacement_span(
        text,
        start,
        start + len(quote),
        "Nor should any conclusion be drawn from these pages that takes a position "
        "for or against any philosophical doctrine.",
    )
    assert text[span[0] : span[1]].startswith("Nor should any conclusion be drawn from the")
    assert text[span[0] : span[1]].endswith("of whatever kind")
    # A correction that shares nothing with its surroundings keeps the quoted span.
    assert replacement_span(text, start, start + len(quote), "of no doctrine") == (
        start,
        start + len(quote),
    )
