"""A production walks a level from probe to verdict; the steps it starts are proven elsewhere."""

from datetime import timedelta
from types import SimpleNamespace

import pytest
from django.utils import timezone

from almonium_book_processor.catalog.models import (
    Chapter,
    Edition,
    PipelineRun,
    QAWarning,
    Work,
)
from almonium_book_processor.catalog.production import advance, backed, queue_production

pytestmark = pytest.mark.django_db
CATALOG = "almonium_book_processor.catalog"


class World:
    """What the steps a production starts would report, set by each test."""

    def __init__(self, source):
        self.source = source
        self.analysis = {}  # edition id -> projection state
        self.ladder = {"B2": "untried", "B1": "untried"}
        self.above = []  # chapters the judges read above the target, per reading of the gate
        self.audit = "none"
        self.audit_touched = timezone.now()
        self.findings = []
        self.reached = True
        self.calls = []

    def edition_for(self, level):
        edition = Edition.objects.create(
            work=self.source.work,
            source_edition=self.source,
            slug=f"book-{level.lower()}",
            language="en",
            edition_type=Edition.EditionType.ADAPTATION,
            status=Edition.Status.REVIEW,
        )
        Chapter.objects.create(edition=edition, sequence=1, title="1")
        Chapter.objects.create(edition=edition, sequence=2, title="2")
        return edition


@pytest.fixture
def world(monkeypatch):
    work = Work.objects.create(slug="book", title="A book", author="Author")
    source = Edition.objects.create(
        work=work, slug="book-en", language="en", status=Edition.Status.READY, cefr_level="C1"
    )
    world = World(source)
    world.analysis[str(source.id)] = "complete"

    def patch(name, value):
        monkeypatch.setattr(f"{CATALOG}.{name}", value)

    patch("tasks.produce_edition.delay", lambda run_id: world.calls.append("tick"))
    patch(
        "chapter_analysis.analysis_context",
        lambda edition: {"projection_state": world.analysis.get(str(edition.id), "pending")},
    )

    def queue_analysis(edition_id):
        world.calls.append("analysis")
        world.analysis[str(edition_id)] = "complete"

    patch("chapter_analysis.queue_analysis", queue_analysis)
    patch(
        "adaptation_floor.ladder",
        lambda edition: [
            {"level": level, "state": state, "can_probe": state == "untried", "note": "it says"}
            for level, state in world.ladder.items()
        ],
    )

    def queue_probe(source_id, level):
        world.calls.append(f"probe {level}")
        world.ladder[level] = "probe_passed"

    patch("adaptation_floor.queue_probe", queue_probe)

    def queue_book(source_id, *, target_level):
        world.calls.append(f"book {target_level}")
        edition = world.edition_for(target_level)
        return PipelineRun.objects.create(
            edition=edition,
            stage=PipelineRun.Stage.ADAPT,
            processor_version="b2-book-v1",
            input_hash="",
            idempotency_key=f"book-{target_level}",
            status=PipelineRun.Status.SUCCEEDED,
        )

    patch("book_adaptation.queue_book", queue_book)

    def quality(edition, analysis=None):
        above = world.above.pop(0) if world.above else []
        return {
            "adaptation_target": "B2",
            "adaptation_blocker": "Target not achieved." if above else "",
            "adaptation_above_chapters": above,
        }

    patch("adaptation_quality.adaptation_quality", quality)
    patch("adaptation_quality.adaptation_target", lambda edition: "B2")

    def changed(edition, what):
        # a change of text leaves the judges' reading of the edition out of date
        world.calls.append(what)
        world.analysis[str(edition.id)] = "stale"

    patch(
        "adaptation_wording.spot_fix_chapter",
        lambda edition, chapter: (
            changed(edition, f"paragraphs {chapter.sequence}") or {"changed": 1, "skipped": []}
        ),
    )
    patch(
        "adaptation_wording.revise_chapter",
        lambda edition, chapter, verdict: (
            changed(edition, f"chapter {chapter.sequence}") or {"applied": True}
        ),
    )
    patch("adaptation_wording.check_chapter", lambda edition, chapter: {"max_level": "C1"})
    patch(
        "fidelity_audit.audit_context",
        lambda edition: {
            "fidelity_audit_state": world.audit,
            "fidelity_audit_run": SimpleNamespace(updated_at=world.audit_touched),
        },
    )

    def queue_audit(edition_id):
        world.calls.append("audit")
        world.audit = "current"

    patch("fidelity_audit.queue_edition_audit", queue_audit)
    patch("fidelity_audit.open_findings", lambda edition: list(world.findings))

    def apply(*, edition, reviewer, severities, only, carry):
        changed(edition, f"apply {len(only)} carry={carry} by={reviewer}")
        world.findings = [f for f in world.findings if f.id not in only]
        world.audit = "stale"
        return len(only)

    patch("services.apply_fidelity_findings", apply)
    patch(
        "adaptation_floor.edition_gates",
        lambda edition: {
            "reached": world.reached,
            "difficulty_note": "",
            "fidelity_ok": world.reached,
            "fidelity_state": world.audit,
            "fidelity_open_findings": 0 if world.reached else 2,
        },
    )
    patch("adaptation_floor.refresh_adaptation_floor", lambda work: work)
    return world


def finding(pk, *, backed_by_both):
    evidence = {"raised_by": ["a", "b"] if backed_by_both else ["a"]}
    return SimpleNamespace(id=pk, can_apply=True, suggested_text="better", evidence=evidence)


def run_to_the_end(run, limit=60):
    for _ in range(limit):
        if advance(run.id):
            break
    run.refresh_from_db()
    return run


def test_a_level_is_carried_from_its_probe_to_a_signed_off_edition(world):
    run = run_to_the_end(queue_production(world.source.id, ["B2"]))

    assert world.calls == ["probe B2", "book B2", "analysis", "audit"]
    assert run.status == "succeeded"
    assert run.summary["outcomes"]["B2"]["outcome"] == "ready"
    # signed off as the gates stand, with no person recorded
    edition = Edition.objects.get(slug="book-b2")
    assert edition.status == Edition.Status.READY
    decision = edition.review_decisions.get()
    assert decision.reviewer is None and "No person reviewed" in decision.notes


def test_the_adaptations_own_review_items_are_closed_and_another_kind_holds_the_book(world):
    world.audit = "running"
    run = queue_production(world.source.id, ["B2"])
    assert not advance(run.id)  # the probe is running
    assert not advance(run.id)  # written, read by the judges, and now with the auditors
    world.audit = "current"
    edition = Edition.objects.get(slug="book-b2")
    QAWarning.objects.create(
        edition=edition, code="adaptation_fidelity_review", severity="warning", message="Read it."
    )
    ours = QAWarning.objects.get(edition=edition)

    assert run_to_the_end(run).status == "succeeded"
    ours.refresh_from_db()
    assert ours.resolved_at is not None and ours.resolved_by is None

    other = queue_production(world.source.id, ["B2"])
    world.ladder["B2"] = "generated"
    edition.status = Edition.Status.REVIEW
    edition.save()
    QAWarning.objects.create(
        edition=edition, code="unsupported_markup", severity="warning", message="Look."
    )

    other = run_to_the_end(other)

    assert other.status == "failed"
    assert "another kind are open: unsupported_markup" in other.error


def test_a_failed_probe_holds_the_level_and_the_levels_below_are_not_attempted(world):
    world.ladder["B2"] = "probe_failed"

    run = run_to_the_end(queue_production(world.source.id, ["B1", "B2"]))

    assert run.summary["levels"] == ["B2", "B1"]  # down the ladder, whatever order was asked
    assert run.status == "failed" and run.error.startswith("Held at B2: The B2 probe failed")
    assert run.summary["outcomes"]["B1"]["outcome"] == "not attempted"
    assert "book B2" not in world.calls


def test_a_chapter_above_the_target_is_mended_by_paragraph_then_whole_then_holds_the_book(
    world,
):
    world.above = [[2], [2], [2]]

    run = run_to_the_end(queue_production(world.source.id, ["B2"]))

    assert [call for call in world.calls if call.startswith(("paragraphs", "chapter"))] == [
        "paragraphs 2",
        "chapter 2",
    ]
    assert run.status == "failed"
    assert "Chapter(s) 2 still read above B2" in run.error
    # every change sends the edition back to the judges before anything else looks at it
    assert world.calls.count("analysis") == 3


def test_corrections_both_models_stand_behind_are_written_in_and_the_audit_reads_again(world):
    world.findings = [finding(1, backed_by_both=True), finding(2, backed_by_both=False)]

    run = run_to_the_end(queue_production(world.source.id, ["B2"]))

    assert "apply 1 carry=False by=None" in world.calls
    # the audit was stale after the corrections and ran again; the lone finding stays open
    assert world.calls.count("audit") == 2
    assert [f.id for f in world.findings] == [2]
    assert run.status == "succeeded"


def test_an_edition_whose_gates_do_not_pass_is_held_with_what_stands_in_the_way(world):
    world.reached = False

    run = run_to_the_end(queue_production(world.source.id, ["B2"]))

    assert run.status == "failed"
    assert "2 material finding(s) open that could not be corrected automatically" in run.error
    assert Edition.objects.get(slug="book-b2").status == Edition.Status.REVIEW


def test_a_step_nobody_finishes_holds_the_book_instead_of_waiting_for_ever(world):
    world.ladder["B2"] = "probing"
    run = queue_production(world.source.id, ["B2"])
    advance(run.id)
    assert not advance(run.id)
    run.refresh_from_db()
    run.summary["since"] = (timezone.now() - timedelta(hours=4)).isoformat()
    run.save()

    assert advance(run.id)
    run.refresh_from_db()
    assert run.status == "failed" and "Nothing finished 'probe'" in run.error


def test_a_step_that_keeps_breaking_holds_the_book_with_what_it_said(world, monkeypatch):
    def broken(edition):
        raise RuntimeError("the judges are away")

    monkeypatch.setattr(f"{CATALOG}.adaptation_floor.ladder", broken)

    run = run_to_the_end(queue_production(world.source.id, ["B2"]))

    assert run.status == "failed" and "the judges are away" in run.error
    assert sum("trying again" in entry["note"] for entry in run.summary["log"]) == 1


def test_one_production_of_a_source_at_a_time(world):
    first = queue_production(world.source.id, ["B2"])

    assert queue_production(world.source.id, ["B1"]).id == first.id
    with pytest.raises(ValueError, match="Choose the levels"):
        queue_production(world.source.id, ["C1"])


def test_a_finding_is_backed_when_more_than_one_model_stands_behind_it():
    assert backed({"raised_by": ["opus", "sol"]})
    assert backed({"raised_by": ["opus"], "second_opinion": {"material": True}})
    assert not backed({"raised_by": ["opus"], "second_opinion": {"material": False}})
    assert not backed({"raised_by": ["sol"]})
    # a translation review: agreement, unless an adjudicator ruled otherwise
    assert backed({"agreement": "both"}) and backed({"agreement": "confirmed"})
    assert not backed({"agreement": "disputed"})
    assert backed({"agreement": "disputed", "adjudication": {"verdict": "new_fix"}})
    assert not backed({"agreement": "confirmed", "adjudication": {"verdict": "keep"}})


def test_the_source_page_shows_where_a_production_is_and_why_a_level_was_held(client, settings):
    from django.contrib.auth import get_user_model
    from django.urls import reverse

    settings.OPENAI_API_KEY = "fake"
    work = Work.objects.create(slug="shown", title="A book", author="Author")
    source = Edition.objects.create(
        work=work, slug="shown-en", language="en", status=Edition.Status.READY, cefr_level="C1"
    )
    PipelineRun.objects.create(
        edition=source,
        stage=PipelineRun.Stage.ADAPT,
        processor_version="production-v1",
        input_hash="",
        idempotency_key="shown",
        status=PipelineRun.Status.FAILED,
        summary={
            "levels": ["B2", "B1"],
            "step": "probe",
            "outcomes": {
                "B2": {"outcome": "ready", "note": "Both gates passed."},
                "B1": {"outcome": "held", "reasons": ["The B1 probe failed: too much is lost."]},
            },
            "log": [
                {"at": "2026-10-05T21:00:00+00:00", "level": "B1", "step": "probe", "note": "x"}
            ],
        },
    )
    client.force_login(get_user_model().objects.create_user("staff", is_staff=True))

    page = client.get(reverse("catalog:edition-detail", args=[source.id])).content.decode()

    assert "Production of B2, B1" in page
    assert "B1 held: The B1 probe failed: too much is lost." in page


def test_a_job_a_dead_worker_left_running_is_started_again_not_waited_for(world):
    world.audit = "running"
    world.audit_touched = timezone.now() - timedelta(hours=1)

    run = run_to_the_end(queue_production(world.source.id, ["B2"]))

    assert "audit" in world.calls and run.status == "succeeded"
