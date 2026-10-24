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
    record_unreached,
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


def test_one_garbled_sentence_does_not_close_a_level_but_meaning_lost_throughout_does():
    from almonium_book_processor.catalog.adaptation_floor import _faithful

    def review(material, blocks):
        return {"counts": {"material": material, "minor": 0, "uncertain": 0}, "blocks": blocks}

    assert _faithful(review(0, 3))
    # one finding in a chapter of seventeen blocks goes to the editor's queue with the rest
    assert _faithful(review(1, 17))
    assert not _faithful(review(1, 3))
    assert not _faithful(review(3, 17))
    # an old record that does not say how many blocks were read is held to none
    assert not _faithful({"counts": {"material": 1}})


class TwoAuditors:
    """Each auditor's own findings, then the other's verdict on a material one."""

    def __init__(self, by_model, *, confirms):
        self.by_model = by_model
        self.confirms = confirms
        self.calls = []

    def respond(self, body):
        step = body["text"]["format"]["name"]
        self.calls.append((step, body["model"], body["reasoning"]["effort"]))
        data = json.loads(body["input"])
        if step == "fidelity_second_opinion":
            assert all("source" not in finding for finding in data["findings"])
            assert set(data["blocks"]) == {finding["block_id"] for finding in data["findings"]}
            return _response(
                {
                    "verdicts": [
                        {"id": finding["id"], "material": self.confirms, "reason": "second look"}
                        for finding in data["findings"]
                    ]
                }
            )
        present = {pair["block_id"] for pair in data["blocks"]}
        issues = [i for i in self.by_model[body["model"]] if i["block_id"] in present]
        return _response({"issues": issues, "assessment": "Read every pair."})


@pytest.fixture
def two_auditors(settings):
    settings.FIDELITY_AUDITORS = "claude-code:claude-opus-5-5,codex:gpt-6.1-sol:medium"


def test_a_material_finding_one_auditor_raised_holds_only_if_the_other_confirms(
    source, two_auditors
):
    pilot = _pilot(source)
    auditors = TwoAuditors({"claude-opus-5-5": [], "gpt-6.1-sol": [MATERIAL]}, confirms=False)

    review = audit_pilot(pilot.id, provider=auditors)

    # both read the whole pilot at their own effort, then Opus is asked about sol's finding
    assert auditors.calls == [
        ("fidelity_review", "claude-opus-5-5", "high"),
        ("fidelity_review", "gpt-6.1-sol", "medium"),
        ("fidelity_second_opinion", "claude-opus-5-5", "medium"),
    ]
    assert review["model"] == "claude-opus-5-5 + gpt-6.1-sol"
    assert review["counts"] == {"material": 0, "minor": 0, "uncertain": 1}
    issue = review["issues"][0]
    assert issue["raised_by"] == ["gpt-6.1-sol"]
    assert issue["second_opinion"] == {
        "by": "claude-opus-5-5",
        "material": False,
        "reason": "second look",
    }
    # every call is in the ledger at the share of the plan it used
    assert len(review["ai_run_ids"]) == 3 and float(review["cost_usd"]) > 0
    assert audit_pilot(pilot.id, provider=auditors) == review
    assert len(auditors.calls) == 3
    # a probe audited this way says so
    from almonium_book_processor.catalog.adaptation_floor import probe_spec

    assert probe_spec("B2", "en")["audit_model"] == "claude-opus-5-5 + gpt-6.1-sol"


def test_a_confirmed_material_finding_holds_the_gate(source, two_auditors):
    pilot = _pilot(source)
    auditors = TwoAuditors({"claude-opus-5-5": [MATERIAL], "gpt-6.1-sol": []}, confirms=True)

    review = audit_pilot(pilot.id, provider=auditors)

    assert review["counts"]["material"] == 1
    assert review["issues"][0]["second_opinion"]["by"] == "gpt-6.1-sol"
    assert review["issues"][0]["second_opinion"]["material"] is True


def test_a_finding_both_auditors_raised_is_kept_once_at_the_stricter_severity(source, two_auditors):
    pilot = _pilot(source)
    auditors = TwoAuditors(
        {"claude-opus-5-5": [{**MATERIAL, "severity": "minor"}], "gpt-6.1-sol": [MATERIAL]},
        confirms=False,
    )

    review = audit_pilot(pilot.id, provider=auditors)

    assert len(review["issues"]) == 1
    assert review["issues"][0]["raised_by"] == ["claude-opus-5-5", "gpt-6.1-sol"]
    assert review["counts"]["material"] == 1
    # agreement needs no second opinion
    assert [step for step, _, _ in auditors.calls] == ["fidelity_review", "fidelity_review"]


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


def test_probe_never_samples_a_chapter_that_is_only_verse(source):
    # a dedication poem is kept whole by rule: the probe could not adapt it
    source.blocks.filter(chapter__sequence=1).update(block_type="verse_line")
    assert [c.sequence for c in probe_sample(source)] == [2, 3, 4]


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


def test_the_book_takes_the_chapters_its_probe_wrote_and_writes_only_the_rest(source):
    probe = queue_probe(source.id, "B2")
    run_probe(probe.id, provider=Generator(), judge=Judge("B2"), auditor=Auditor([]))
    probed = [
        result["chapter_id"] for result in PipelineRun.objects.get(pk=probe.id).summary["results"]
    ]
    writer = Generator()

    book = queue_book(source.id)
    run_book(book.id, provider=writer)

    book.refresh_from_db()
    assert book.status == "succeeded"
    assert book.summary["from_probe"] == sorted(probed)
    # the probe wrote three of the chapters; the book pays for the others only
    assert writer.calls == source.chapters.count() - 3
    edition = Edition.objects.get(pk=book.edition_id)
    assert edition.blocks.count() == source.blocks.count()


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


class RevisingGenerator(Generator):
    def __init__(self):
        super().__init__()
        self.instructions = []

    def respond(self, body):
        self.instructions.append(body["instructions"])
        return super().respond(body)


class FirstDraftJudge(Judge):
    """Reads a first draft at one level and its revision at another."""

    def __init__(self, first, revised):
        super().__init__(first)
        self.first, self.revised = first, revised

    def respond(self, body):
        self.level = self.first if self.calls % 2 == 0 else self.revised
        return super().respond(body)


def test_a_chapter_read_above_its_target_goes_back_to_the_adapter_once(source):
    run = queue_probe(source.id, "B2")
    generator = RevisingGenerator()

    run_probe(run.id, provider=generator, judge=FirstDraftJudge("C1", "B2"), auditor=Auditor())

    run.refresh_from_db()
    assert run.summary["verdict"] == "passed"
    # every chapter was written twice: the draft, then the revision the judges read at B2
    assert generator.calls == 6
    assert all(r["revised_from"]["level"] == "C1" for r in run.summary["results"])
    assert all(r["judge_max_level"] == "B2" for r in run.summary["results"])
    # the adapter was told what the judges cited, and to keep the meaning
    feedback = generator.instructions[1]
    assert "EDITORIAL CORRECTIONS FROM THE REVIEWER" in feedback
    assert (
        "at C1, above B2" in feedback and "\u201cBefore dawn\u201d: Direct narration." in feedback
    )
    assert "Keep every idea" in feedback
    assert "EDITORIAL CORRECTIONS" not in generator.instructions[0]


def test_a_revision_the_judges_read_no_easier_leaves_the_first_draft_standing(source):
    run = queue_probe(source.id, "B2")
    generator = RevisingGenerator()

    run_probe(run.id, provider=generator, judge=Judge("C1"), auditor=Auditor())

    run.refresh_from_db()
    assert run.summary["verdict"] == "failed"
    assert generator.calls == 6
    assert all("revised_from" not in r for r in run.summary["results"])


def test_feedback_names_the_cited_words_and_passages_but_not_the_content_notes():
    from almonium_book_processor.catalog.adaptation_floor import level_feedback

    assessment = {
        "max_level": "B2",
        "windows": [
            {
                "hard_words": [{"surface": "wretch"}, {"surface": "pleas"}, {"surface": "wretch"}],
                "evidence": [
                    {
                        "quote": "Human laws are bloody",
                        "dimension": "syntax",
                        "explanation": "Long.",
                    },
                    {"quote": "I will feed it", "dimension": "content", "explanation": "Violence."},
                ],
            }
        ],
    }

    feedback = level_feedback(assessment, "B1")

    assert "Do not use these words" in feedback and "wretch, pleas." in feedback
    assert "\u201cHuman laws are bloody\u201d: Long." in feedback
    # what a passage is about is the author's; only its wording is the adapter's to change
    assert "I will feed it" not in feedback


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
    # The sentence keeps its own period: the span and the words to write in stop before it.
    assert (material.start_offset, material.end_offset) == (0, len("Before dawn, he left"))
    assert material.original_text == "Before dawn, he left"
    assert material.suggested_text == "Before dawn, he had already left"
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


def test_chosen_corrections_can_be_written_in_and_left_for_the_auditors_to_read_again(
    adaptation, django_capture_on_commit_callbacks
):
    from almonium_book_processor.catalog.services import apply_fidelity_findings

    run = queue_edition_audit(adaptation.id)
    second = {
        **MATERIAL,
        "block_id": "c1.b2",
        "source_quote": "afraid",
        "adapted_quote": "afraid",
        "severity": "minor",
        "suggested_correction": "terrified",
    }
    run_edition_audit(run.id, provider=Auditor([MATERIAL, second]))
    material = adaptation.text_quality_findings.get(code="fidelity_material")

    with django_capture_on_commit_callbacks(execute=True):
        applied = apply_fidelity_findings(
            edition=adaptation,
            reviewer=None,
            severities=["material", "minor", "uncertain"],
            only={material.id},
            carry=False,
        )

    assert applied == 1
    # only the finding named was written in, by nobody
    assert adaptation.blocks.get(block_id="c1.b2").text == "He was afraid."
    assert adaptation.block_revisions.get().editor is None
    # and the audit is not kept current over its own words: the chapter is read again
    assert audit_context(adaptation)["fidelity_audit_state"] == "stale"


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
    # This book was never judged: a fix refreshes a verdict, it does not buy the first one.
    assert not adaptation.pipeline_runs.filter(stage="chapter_analysis").exists()
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
    assert "Probe B2 on 3 chapters" in page
    assert "Probe B1" not in page and "Reach the level above first" in page
    response = client.post(
        reverse("catalog:queue-floor-probe", args=[source.id]), {"target_level": "B2"}
    )
    assert response.status_code == 302
    assert source.pipeline_runs.filter(processor_version=PROBE_VERSION, status="queued").exists()
    page = client.get(reverse("catalog:edition-detail", args=[source.id])).content.decode()
    assert "Probing" in page and "Probe B2 on 3 chapters" not in page

    book = queue_book(source.id)
    run_book(book.id, provider=Generator())
    adaptation = Edition.objects.get(pk=book.edition_id)
    page = client.get(reverse("catalog:edition-detail", args=[adaptation.id])).content.decode()
    assert 'id="fidelity-audit"' in page and 'Audit fidelity<span class="cost">' in page
    assert "adaptation-ladder" not in page
    response = client.post(reverse("catalog:queue-fidelity-audit", args=[adaptation.id]))
    assert response.status_code == 302
    audit = adaptation.pipeline_runs.get(processor_version=AUDIT_VERSION)
    page = client.get(reverse("catalog:edition-detail", args=[adaptation.id])).content.decode()
    assert 'Audit fidelity<span class="cost">' not in page and "Running" in page
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
    # a small point one model raised alone is listed apart from what needs a decision
    assert context["fidelity_findings"] == []
    assert context["fidelity_optional"][0].source_text == "Ere dawn, he departed."
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
    assert tag(text, "he left", "he had already left") == (
        "Before dawn, he <ins>had already </ins>left."
    )
    segments, placed = change_preview(text, "not there ... at all", "He was terrified.")
    assert not placed and any(s["op"] == "delete" for s in segments)
    # Word by word inside the clause the apply will replace: two changes, not one blot.
    text = (
        "I have promised that someone will watch for it and give him immediate notice "
        "if any new object appears in sight. Then we parted."
    )
    fix = (
        "I have promised that someone will watch for the other traveller and give him "
        "immediate notice if anything new appears in sight."
    )
    assert tag(text, "I have promised that someone will watch for it", fix) == (
        "I have promised that someone will watch for <del>it</del><ins>the other traveller</ins> "
        "and give him immediate notice if <del>any new object</del><ins>anything new</ins> "
        "appears in sight."
    )
    # A rewritten clause with a stray word in common still reads as one replacement.
    text = "He listened to all my arguments in favour of my possible success, and more."
    fix = "arguments that I would eventually succeed"
    assert tag(text, "arguments in favour of my possible success", fix) == (
        "He listened to all my arguments <del>in favour of my possible success,</del>"
        "<ins>that I would eventually succeed,</ins> and more."
    )


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


def test_an_edition_audited_by_two_auditors_queues_what_they_raised_and_said(
    adaptation, two_auditors
):
    minor = {**MATERIAL, "block_id": "c2.b1", "severity": "minor"}
    auditors = TwoAuditors(
        {"claude-opus-5-5": [minor], "gpt-6.1-sol": [MATERIAL, {**MATERIAL, "block_id": "c3.b1"}]},
        confirms=False,
    )

    audit = queue_edition_audit(adaptation.id)
    run_edition_audit(audit.id, provider=auditors)

    audit.refresh_from_db()
    assert (
        audit.status == "succeeded"
        and audit.summary["review"]["model"] == "claude-opus-5-5 + gpt-6.1-sol"
    )
    # every chapter was read by both; Opus was asked about each chapter's finding it did not raise
    steps = [step for step, _, _ in auditors.calls]
    assert steps.count("fidelity_review") == 8 and steps.count("fidelity_second_opinion") == 2
    findings = {f.stable_block_id: f for f in adaptation.text_quality_findings.all()}
    assert set(findings) == {"c1.b1", "c2.b1", "c3.b1"}
    # what only one auditor called material and the other did not confirm is kept as uncertain
    assert findings["c1.b1"].evidence["severity"] == "uncertain"
    assert findings["c1.b1"].evidence["raised_by"] == ["gpt-6.1-sol"]
    assert findings["c1.b1"].evidence["second_opinion"]["by"] == "claude-opus-5-5"
    assert findings["c2.b1"].evidence["raised_by"] == ["claude-opus-5-5"]
    # nothing material is open, so the fidelity gate is not held
    assert audit.summary["review"]["counts"]["material"] == 0
    from almonium_book_processor.catalog.fidelity_audit import fidelity_gate
    from almonium_book_processor.catalog.services import apply_fidelity_findings

    assert audit_context(adaptation)["fidelity_audit_state"] == "current"
    assert fidelity_gate(adaptation)[0] is True
    # writing in the auditors' own correction keeps their audit current for the new text
    reviewer = get_user_model().objects.create_user("panel-editor", is_staff=True)
    apply_fidelity_findings(edition=adaptation, reviewer=reviewer, severities=["minor"])
    assert adaptation.blocks.get(block_id="c2.b1").text == "Before dawn, he had already left."
    assert audit_context(adaptation)["fidelity_audit_state"] == "current"


def test_a_correction_that_would_repeat_the_sentence_beside_it_is_not_ready_to_apply():
    from almonium_book_processor.catalog.fidelity_audit import repeats_text

    # the auditor quoted the second sentence and wrote a correction that takes in the first
    text = (
        "I gathered around me the tools I needed to give life. "
        "I hoped to put a spark of life into the lifeless thing at my feet. It was one."
    )
    quote = "I hoped to put a spark of life into the lifeless thing at my feet"
    start = text.index(quote)
    merged = (
        "I gathered around me the tools I needed so that I could put a spark of life into the "
        "lifeless thing at my feet"
    )
    assert repeats_text(text, start, start + len(quote), merged)
    # a correction that ends the sentence, pasted over its first words, leaves the old tail
    text = "I hoped his words would explain these unusual sights."
    quote = "I hoped his words would explain"
    assert repeats_text(
        text, 0, len(quote), "I waited to learn from his words what these sights meant."
    )
    # an ordinary correction of the quoted words is ready
    text = "It stood a little more than one old unit of distance from the city. We lived there."
    quote = "a little more than one old unit of distance from the city"
    start = text.index(quote)
    assert not repeats_text(
        text, start, start + len(quote), "a little more than three miles from the city"
    )


def test_such_a_correction_is_queued_for_a_hand_edit_not_for_one_click(adaptation):
    block = adaptation.blocks.get(block_id="c1.b2")
    # the correction takes in the sentence before, but not word for word, so the span cannot
    # simply be widened to cover it
    block.text = (
        "He packed his bags that night to be ready. He hoped to leave before the others woke."
    )
    block.save()
    issue = {
        **MATERIAL,
        "block_id": "c1.b2",
        "source_quote": "He was afraid.",
        "adapted_quote": "He hoped to leave before the others woke",
        "suggested_correction": (
            "He packed his bags that night so that he could leave before the others woke"
        ),
    }

    audit = queue_edition_audit(adaptation.id)
    run_edition_audit(audit.id, provider=Auditor([issue]))

    finding = adaptation.text_quality_findings.get(stable_block_id="c1.b2")
    # the editor still sees what the auditor proposed, but nothing is offered to paste in
    assert finding.suggested_text == ""
    assert finding.evidence["suggested_correction"].startswith("He packed his bags that night so")


def _analysed(adaptation, level):
    from almonium_book_processor.catalog.chapter_analysis import analyze_chapters, queue_analysis

    analysis = queue_analysis(str(adaptation.id))
    analyze_chapters(str(analysis.id), provider=Judge(level))
    return analysis


def test_the_judges_wording_level_is_the_adaptations_where_they_read_the_current_text(
    adaptation,
):
    from almonium_book_processor.catalog.adaptation_quality import adaptation_quality
    from almonium_book_processor.catalog.adaptation_wording import check_edition, wording_levels

    # the library's chapter analysis reads every chapter above the B2 target
    _analysed(adaptation, "C1")
    assert "not achieved" in adaptation_quality(adaptation)["adaptation_blocker"]
    judge = Judge("B2")

    verdicts = check_edition(adaptation, provider=judge)

    assert {v["max_level"] for v in verdicts.values()} == {"B2"}
    assert set(wording_levels(adaptation).values()) == {"B2"}
    # the pilot's judges read the wording at the target, and theirs is the level that counts
    quality = adaptation_quality(adaptation)
    assert quality["adaptation_blocker"] == "" and quality["adaptation_above_chapters"] == []
    # a text they have read is not read again
    calls = judge.calls
    check_edition(adaptation, provider=judge)
    assert judge.calls == calls
    # a chapter whose text changed since is theirs no longer
    changed = adaptation.blocks.get(block_id="c2.b1")
    changed.text = "Before dawn, he went away."
    changed.save()
    assert str(changed.chapter_id) not in wording_levels(adaptation)


def test_a_chapter_read_above_the_target_is_revised_and_applied_only_at_the_target(
    adaptation, monkeypatch
):
    from almonium_book_processor.catalog.adaptation_wording import (
        check_chapter,
        revise_chapter,
    )

    monkeypatch.setattr(
        "almonium_book_processor.catalog.tasks.reassess_applied_pilot.delay", lambda _: None
    )
    chapter = adaptation.chapters.get(sequence=1)
    verdict = check_chapter(adaptation, chapter, provider=Judge("C1"))

    class Reviser(RevisingGenerator):
        def respond(self, body):
            response = super().respond(body)
            content = response["output"][0]["content"][0]
            content["text"] = content["text"].replace("he left.", "he went away.")
            return response

    generator = Reviser()

    refused = revise_chapter(adaptation, chapter, verdict, provider=generator, judge=Judge("C1"))

    # the adapter was told what the judges cited; the judges read its revision no easier
    assert "at C1, above B2" in generator.instructions[0]
    assert refused["applied"] is False and "read at C1" in refused["reason"]

    # another chapter, whose revision the judges read at the target
    second = adaptation.chapters.get(sequence=2)
    verdict = check_chapter(adaptation, second, provider=Judge("C1"))

    applied = revise_chapter(adaptation, second, verdict, provider=generator, judge=Judge("B2"))

    assert applied == {"applied": True, "level": "B2", "pilot_id": applied["pilot_id"]}
    block = adaptation.blocks.get(block_id="c2.b1")
    assert block.text == "Before dawn, he went away."
    revision = block.revisions.latest("created_at")
    assert "Applied automatically" in revision.notes and "No person has reviewed" in revision.notes


class CitingJudge(Judge):
    """Reads at C1 and cites a hard word, a passage, and what the passage is about."""

    def respond(self, body):
        response = super().respond(body)
        content = response["output"][0]["content"][0]
        result = json.loads(content["text"])
        block_id = result["evidence"][0]["block_id"]
        result["hard_words"] = [
            {"block_id": block_id, "surface": "dawn", "explanation": "The first light of day."}
        ]
        result["evidence"].append(
            {
                "block_id": block_id,
                "quote": "he left",
                "dimension": "content",
                "explanation": "A departure.",
            }
        )
        result["content_flags"] = ["Departure"]
        content["text"] = json.dumps(result)
        return response


class SpotFixer:
    def __init__(self, text):
        self.text = text
        self.asked = []

    def respond(self, body):
        payload = json.loads(body["input"])
        self.asked.append({"instructions": body["instructions"], **payload})
        return _response(
            {
                "blocks": [
                    {"block_id": p["block_id"], "text": self.text, "reason": "A plainer verb."}
                    for p in payload["paragraphs"]
                ]
            }
        )


def test_the_difficulty_review_item_clears_when_the_judges_read_every_chapter_at_the_target(
    adaptation,
):
    from django.core.management import call_command

    from almonium_book_processor.catalog.adaptation_quality import DIFFICULTY_WARNING
    from almonium_book_processor.catalog.adaptation_wording import check_edition

    # the library's chapter analysis reads the book above its target and opens the item
    _analysed(adaptation, "C1")
    item = adaptation.warnings.get(code=DIFFICULTY_WARNING)
    assert item.resolved_at is None
    # the pilot's judges read every chapter at the target
    check_edition(adaptation, provider=Judge("B2"))

    call_command("check_adaptation_wording", adaptation.slug, workers=1)

    item.refresh_from_db()
    assert item.resolved_at is not None


def test_only_the_paragraphs_the_judges_cited_are_rewritten(adaptation):
    from almonium_book_processor.catalog.adaptation_wording import check_chapter, spot_fix_chapter

    chapter = adaptation.chapters.get(sequence=1)
    check_chapter(adaptation, chapter, provider=CitingJudge("C1"))
    fixer = SpotFixer("Before dawn, he went away.")

    outcome = spot_fix_chapter(adaptation, chapter, provider=fixer)

    assert outcome == {"changed": 1, "skipped": [], "block_ids": ["c1.b1"]}
    # the adapter saw the one cited paragraph, with its original and what was cited in it
    asked = fixer.asked[0]
    assert "CEFR B2 reader" in asked["instructions"]
    assert asked["paragraphs"] == [
        {
            "block_id": "c1.b1",
            "original": "Ere dawn, he departed.",
            "adaptation": "Before dawn, he left.",
            # the word and the passage, not what the passage is about: that is the author's
            "notes": ["word: dawn", "passage: \u201cBefore dawn\u201d: Direct narration."],
        }
    ]
    assert adaptation.blocks.get(block_id="c1.b1").text == "Before dawn, he went away."
    # the rest of the chapter, and the other chapters, stand as they were
    assert adaptation.blocks.get(block_id="c1.b2").text == "He was afraid."
    assert adaptation.blocks.get(block_id="c2.b1").text == "Before dawn, he left."
    revision = adaptation.blocks.get(block_id="c1.b1").revisions.latest("created_at")
    assert "Rewritten automatically" in revision.notes and "A plainer verb." in revision.notes
    # the new text has not been read by the judges, so nothing is cited in it yet
    again = spot_fix_chapter(adaptation, chapter, provider=fixer)
    assert again["changed"] == 0 and len(fixer.asked) == 1


def test_a_rewrite_that_lost_most_of_the_paragraph_is_not_written_in(adaptation):
    from almonium_book_processor.catalog.adaptation_wording import check_chapter, spot_fix_chapter

    chapter = adaptation.chapters.get(sequence=1)
    check_chapter(adaptation, chapter, provider=CitingJudge("C1"))

    outcome = spot_fix_chapter(adaptation, chapter, provider=SpotFixer("He left."))

    assert outcome["changed"] == 0 and "c1.b1: length 0.36" in outcome["skipped"][0]
    assert adaptation.blocks.get(block_id="c1.b1").text == "Before dawn, he left."


def test_a_chapter_the_judges_read_at_the_target_has_nothing_to_mend(adaptation):
    from almonium_book_processor.catalog.adaptation_wording import check_chapter, spot_fix_chapter

    chapter = adaptation.chapters.get(sequence=1)
    check_chapter(adaptation, chapter, provider=CitingJudge("B2"))
    fixer = SpotFixer("Before dawn, he went away.")

    assert spot_fix_chapter(adaptation, chapter, provider=fixer)["changed"] == 0
    assert fixer.asked == []


def test_a_corrected_phrase_keeps_the_judges_reading_and_a_rewritten_chapter_does_not(
    adaptation, django_capture_on_commit_callbacks
):
    from almonium_book_processor.catalog.adaptation_wording import (
        carry_wording_forward,
        check_edition,
        wording_levels,
    )
    from almonium_book_processor.catalog.services import revise_block_text

    reviewer = get_user_model().objects.create_user("phrase-editor", is_staff=True)
    # a real chapter is pages long; one corrected phrase is a sliver of it
    filler = " ".join(f"Sentence number {i} keeps the chapter long." for i in range(40))
    for chapter in adaptation.chapters.filter(sequence__in=[1, 2]):
        ContentBlock.objects.create(
            edition=adaptation,
            chapter=chapter,
            sequence=9,
            block_id=f"c{chapter.sequence}.b9",
            block_type="paragraph",
            text=filler,
            align_group=uuid.uuid4(),
        )
    _analysed(adaptation, "B2")
    judge = Judge("B2")
    check_edition(adaptation, provider=judge)
    assert len(wording_levels(adaptation)) == 4
    calls = judge.calls

    with django_capture_on_commit_callbacks(execute=True):
        revise_block_text(
            edition=adaptation,
            block_id=adaptation.blocks.get(block_id="c1.b9").id,
            revised_text=filler.replace("number 3 keeps", "number three keeps"),
            editor=reviewer,
        )

    # the edit itself carried the reading: the chapter is still the judges', and nobody was asked
    first = adaptation.chapters.get(sequence=1)
    assert wording_levels(adaptation)[str(first.id)] == "B2"
    check_edition(adaptation, provider=judge)
    assert judge.calls == calls
    kept = adaptation.pipeline_runs.filter(
        processor_version="adaptation-wording-v1", summary__chapter_id=str(first.id)
    ).first()
    assert kept.summary["carried"][0]["change"] < 0.02

    # a reading above the target is not carried: the edit was meant to bring the chapter down
    third = adaptation.chapters.get(sequence=3)
    above = adaptation.pipeline_runs.get(
        processor_version="adaptation-wording-v1", summary__chapter_id=str(third.id)
    )
    above.summary = {
        **above.summary,
        "assessment": {**above.summary["assessment"], "max_level": "C1"},
    }
    above.save()
    with django_capture_on_commit_callbacks(execute=True):
        revise_block_text(
            edition=adaptation,
            block_id=adaptation.blocks.get(block_id="c3.b2").id,
            revised_text="He was very afraid.",
            editor=reviewer,
        )
    assert str(third.id) not in wording_levels(adaptation)
    calls += 1  # the judges read that chapter again when asked

    # a paragraph rewritten is more than a phrase: that chapter is theirs no longer
    with django_capture_on_commit_callbacks(execute=True):
        revise_block_text(
            edition=adaptation,
            block_id=adaptation.blocks.get(block_id="c2.b9").id,
            revised_text="Before dawn " + " ".join(["word"] * 200),
            editor=reviewer,
        )
    second = adaptation.chapters.get(sequence=2)
    assert str(second.id) not in wording_levels(adaptation)
    assert carry_wording_forward(adaptation) == []
    check_edition(adaptation, provider=judge)
    assert judge.calls == calls + 1


def test_a_reading_that_failed_starts_again_after_another_chapter_changed(adaptation):
    from almonium_book_processor.catalog.adaptation_wording import check_chapter

    first = adaptation.chapters.get(sequence=1)

    class Broken:
        def respond(self, body):
            return {"status": "incomplete", "usage": {}, "output": []}

    with pytest.raises(ValueError):
        check_chapter(adaptation, first, provider=Broken())
    # the book moves on: another chapter is edited before the reading is tried again
    other = adaptation.blocks.get(block_id="c2.b2")
    other.text = "He was very afraid."
    other.save()

    assert check_chapter(adaptation, first, provider=Judge("B2"))["max_level"] == "B2"


def test_only_the_windows_read_above_the_target_are_mended(adaptation):
    from almonium_book_processor.catalog.adaptation_wording import (
        WORDING_VERSION,
        citations,
        text_hash,
    )
    from almonium_book_processor.catalog.chapter_analysis import chapter_blocks

    chapter = adaptation.chapters.get(sequence=1)

    def window(level, block_id, word):
        return {
            "cefr_estimate": level,
            "hard_words": [{"block_id": block_id, "surface": word, "explanation": "A word."}],
            "evidence": [],
        }

    PipelineRun.objects.create(
        edition=adaptation,
        stage="adapt",
        processor_version=WORDING_VERSION,
        input_hash="x",
        idempotency_key="long-chapter-wording",
        status="succeeded",
        summary={
            "chapter_id": str(chapter.id),
            "text_hash": text_hash(chapter_blocks(chapter)),
            "assessment": {
                "max_level": "C1",
                # a long chapter in two windows: the first reads at the target
                "windows": [window("B2", "c1.b1", "dawn"), window("C1", "c1.b2", "afraid")],
            },
        },
    )

    assert citations(adaptation, chapter, "B2") == {"c1.b2": ["word: afraid"]}


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
    # A hand edit of a phrase carries the same way; the editor did not have to ask.
    with django_capture_on_commit_callbacks(execute=True):
        revise_block_text(
            edition=adaptation,
            block_id=adaptation.blocks.get(block_id="c1.b9").id,
            revised_text=filler.replace("number 3 keeps", "number three keeps"),
            editor=reviewer,
        )
    assert analysis_context(adaptation)["projection_state"] == "complete"
    assert (
        not adaptation.pipeline_runs.filter(stage="chapter_analysis")
        .exclude(pk=analysis.pk)
        .exists()
    )
    analysis.refresh_from_db()
    assert len(analysis.summary["carried"]) == 2
    assert judge.calls == judged_calls
    # A rewrite of the block is more than a phrase: a real analysis is queued, and
    # the judge re-reads the rewritten chapter only; the others come from cache.
    with django_capture_on_commit_callbacks(execute=True):
        revise_block_text(
            edition=adaptation,
            block_id=adaptation.blocks.get(block_id="c2.b1").id,
            revised_text="Before dawn " + " ".join(["word"] * 60),
            editor=reviewer,
        )
    queued = adaptation.pipeline_runs.get(stage="chapter_analysis", status="queued")
    analyze_chapters(str(queued.id), provider=judge)
    assert judge.calls == judged_calls + 1
    assert analysis_context(adaptation)["projection_state"] == "complete"


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
    from almonium_book_processor.catalog.fidelity_audit import replacement_span, usable_suggestion

    def applied(text, quote, fix):
        start = text.index(quote)
        s, e, words = replacement_span(text, start, start + len(quote), fix)
        return text[:s] + words + text[e:]

    text = "At night the southern winds blow us quickly towards those shores, and we sleep."
    assert applied(text, "the southern winds", "the strong southern winds blow us quickly") == (
        "At night the strong southern winds blow us quickly towards those shores, and we sleep."
    )
    text = (
        "Nor should any conclusion be drawn from the following pages that favours any "
        "philosophical doctrine of whatever kind; and the opinions are the author's."
    )
    assert applied(
        text,
        "that favours any philosophical doctrine of whatever kind",
        "Nor should any conclusion be drawn from these pages that takes a position "
        "for or against any philosophical doctrine.",
    ) == (
        "Nor should any conclusion be drawn from these pages that takes a position for or "
        "against any philosophical doctrine; and the opinions are the author's."
    )
    # Punctuation and quotation marks stay with the sentence.
    assert applied(
        "It seemed to me. Then night fell.", "seemed", "was beginning to seem to me"
    ) == ("It was beginning to seem to me. Then night fell.")
    assert (
        applied(
            'and do not fear that, when you are ready, I shall appear." He left.',
            "fear that, when you are ready, I shall appear",
            "and do not doubt that I shall appear when you are ready.",
        )
        == 'and do not doubt that I shall appear when you are ready." He left.'
    )
    assert applied('"I want to free you," he said.', "free", "relieve") == (
        '"I want to relieve you," he said.'
    )
    assert applied("He looked into my eyes, and wept.", "looked into", "gazed into my eyes.") == (
        "He gazed into my eyes, and wept."
    )
    assert applied("an offence to the dead; and yet", "an offence", "a sacrilege to the dead.") == (
        "a sacrilege to the dead; and yet"
    )
    # A correction that shares nothing with its surroundings keeps the quoted span.
    assert applied("The wanderer went on.", "wanderer", "vagrant") == "The vagrant went on."
    # Advice is not text to write in.
    assert usable_suggestion('Use "so heedlessly bestowed" or "so carelessly bestowed."') == ""
    assert usable_suggestion("Consider keeping the original.") == ""
    assert usable_suggestion("so heedlessly bestowed") == "so heedlessly bestowed"


UK_SOURCE = "Ще до світанку він вирушив у дорогу, і страх не полишав його ані на мить."
UK_ADAPTED = "Він вийшов у дорогу ще до світанку, і йому весь час було страшно."


def test_an_english_correction_for_a_ukrainian_edition_fails_the_audit(source):
    from almonium_book_processor.ai.output_language import OutputLanguageError

    source.language = "uk"
    source.save(update_fields=["language"])
    source.blocks.filter(text="Ere dawn, he departed.").update(text=UK_SOURCE)

    class UkrainianGenerator(Generator):
        def respond(self, body):
            response = super().respond(body)
            payload = json.loads(response["output"][0]["content"][0]["text"])
            for block in payload["blocks"]:
                if block["text"] == UK_SOURCE:
                    block.update(text=UK_ADAPTED, decision="adapted", reason="Простіше.")
            response["output"][0]["content"][0]["text"] = json.dumps(payload, ensure_ascii=False)
            return response

    pilot = queue_pilot(source.id, source.chapters.first().id, dispatch=False)
    run_pilot(pilot.id, provider=UkrainianGenerator())
    issue = {
        "block_id": "c1.b1",
        "source_quote": "страх не полишав його",
        "adapted_quote": "було страшно",
        "severity": "minor",
        "explanation": "Fear never leaving him is stronger than being scared.",
        "suggested_correction": "and fear did not leave him for a single moment of the way",
    }
    with pytest.raises(OutputLanguageError, match="uk"):
        audit_pilot(pilot.id, provider=Auditor([issue]))
    failed = AIRun.objects.get(prompt_template__name="literary-fidelity-editor")
    assert failed.status == "failed" and failed.error == "OutputLanguageError"
    assert PipelineRun.objects.get(processor_version=AUDIT_VERSION).status == "failed"
    ukrainian = {**issue, "suggested_correction": "і страх ані на мить не полишав його дорогою"}
    review = audit_pilot(pilot.id, provider=Auditor([ukrainian]))
    assert review["counts"]["minor"] == 1 and review["issues"][0]["quote_verified"] is True


def test_a_block_read_as_the_right_language_with_modest_confidence_passes_the_gate():
    from almonium_book_processor.ai.output_language import (
        OutputLanguageError,
        validate_output_language,
    )

    # the whole text must be read as Ukrainian with confidence; one block of it need only be
    # read as Ukrainian, as a short line without the telling letters often is
    whole = "Вона підійшла до вікна і довго дивилася на дорогу, що вела до села."
    plain = "Да, сказав він тихо."  # no і, ї, є, ґ: the detector hesitates between Cyrillic tongues
    validate_output_language([whole, whole, plain], "uk")
    with pytest.raises(OutputLanguageError):
        validate_output_language(
            ["This is plain English prose that is not Ukrainian at all, clearly."], "uk"
        )


def test_a_level_a_production_dropped_stays_not_reached_on_the_ladder(source):
    record_unreached(source, "B2", "Chapter(s) 1, 3 still read above B2 after the rewrites.")
    refresh_adaptation_floor(source.work)

    source.work.refresh_from_db()
    evidence = source.work.adaptation_evidence["levels"]["B2"]
    assert evidence["state"] == "not_reached"
    assert evidence["reasons"] == ["Chapter(s) 1, 3 still read above B2 after the rewrites."]
    rows = ladder(source)
    assert rows[0]["state"] == "not_reached" and not rows[0]["can_probe"]
    assert rows[0]["note"] == "Chapter(s) 1, 3 still read above B2 after the rewrites."
    assert rows[1]["state"] == "untried" and not rows[1]["can_probe"]
    assert reached_levels(source.work) == []
