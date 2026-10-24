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
from almonium_book_processor.catalog.publication import RIGHTS_UNCHECKED, RightsVerdict

pytestmark = pytest.mark.django_db
CATALOG = "almonium_book_processor.catalog"


class World:
    """What the steps a production starts would report, set by each test."""

    def __init__(self, source):
        self.source = source
        self.analysis = {}  # edition id -> projection state
        self.analysis_runs = {}  # edition id -> the analysis run, where one is under way
        self.ladder = {"B2": "untried", "B1": "untried"}
        self.above = []  # chapters the judges read above the target, per reading of the gate
        self.tolerated = []  # of those, the ones the allowance covers, per reading of the gate
        self.dropped = []  # (edition slug, level, reason) of the levels the production dropped
        self.audit = "none"
        self.audit_touched = timezone.now()
        self.findings = []
        self.reached = True
        self.rights = RightsVerdict("FREE", "Free in UA and DE since 1922.", 1922, ["UA", "DE"])
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
    patch("publication.check_rights", lambda edition: world.rights)
    patch(
        "chapter_analysis.analysis_context",
        lambda edition: {
            "projection_state": world.analysis.get(str(edition.id), "pending"),
            "chapter_analysis_run": world.analysis_runs.get(str(edition.id)),
        },
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
        tolerated = world.tolerated.pop(0) if world.tolerated else []
        return {
            "adaptation_target": "B2",
            "adaptation_blocker": "Target not achieved." if above and not tolerated else "",
            "adaptation_above_chapters": above,
            "adaptation_tolerated_chapters": tolerated,
        }

    patch("adaptation_quality.adaptation_quality", quality)
    patch(
        "adaptation_floor.record_unreached",
        lambda source, level, reason, production=None: world.dropped.append((level, reason)),
    )
    patch("adaptation_floor.refresh_adaptation_floor", lambda work: work)
    patch(
        "purge.purge_edition",
        lambda edition, **kwargs: world.calls.append(f"purge {edition.slug}") or edition.delete(),
    )
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

    def repair(edition, chapter, findings):
        changed(edition, f"repair {chapter.sequence} {[f.id for f in findings]}")
        world.findings = [f for f in world.findings if f not in findings]
        world.audit = "stale"
        return {"changed": len(findings), "skipped": []}

    patch("adaptation_wording.repair_chapter", repair)

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


def finding(pk, *, backed_by_both, can_apply=True, code="fidelity_material", block=None):
    evidence = {"raised_by": ["a", "b"] if backed_by_both else ["a"]}
    return SimpleNamespace(
        id=pk,
        can_apply=can_apply,
        suggested_text="better" if can_apply else "",
        evidence=evidence,
        code=code,
        stable_block_id=f"c1.p{pk}",
        block=block or SimpleNamespace(chapter_id=None),
    )


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


def test_a_free_work_is_produced_with_the_verdict_kept(world):
    run = run_to_the_end(queue_production(world.source.id, ["B2"]))

    assert run.status == "succeeded"
    assert run.summary["rights"]["status"] == "FREE"
    assert run.summary["log"][0]["step"] == "rights"
    assert run.summary["log"][0]["note"] == "Rights: free in UA, DE. Free in UA and DE since 1922."


def test_a_protected_work_is_held_before_anything_is_spent_on_it(world):
    reason = "Under copyright in UA and DE until the end of 2046 (by the catalogue's dates)."
    world.rights = RightsVerdict("PROTECTED", reason, 2047, ["UA", "DE"])
    world.analysis[str(world.source.id)] = "pending"

    run = run_to_the_end(queue_production(world.source.id, ["B2", "B1"], languages=["uk"]))

    assert world.calls == []
    assert run.status == "failed"
    assert run.summary["rights"]["status"] == "PROTECTED"
    assert run.summary["outcomes"] == {
        "B2": {"outcome": "held", "reasons": [f"Not prepared: {reason}"]},
        "B1": {"outcome": "not attempted", "reasons": ["B2 was held: the book is not prepared."]},
        "uk": {"outcome": "not attempted", "reasons": ["B2 was held: the book is not prepared."]},
    }
    assert reason in run.error


@pytest.mark.parametrize(
    ("status", "note"),
    [
        ("UNKNOWN", "Rights unknown, going ahead: No death year for the author."),
        (
            RIGHTS_UNCHECKED,
            "Rights not checked, going ahead (publication is checked again): "
            "No death year for the author.",
        ),
    ],
)
def test_an_unsettled_or_unchecked_verdict_goes_ahead_with_its_reason_logged(world, status, note):
    world.rights = RightsVerdict(status, "No death year for the author.")

    run = run_to_the_end(queue_production(world.source.id, ["B2"]))

    assert run.status == "succeeded"
    assert run.summary["rights"]["status"] == status
    assert run.summary["log"][0]["note"] == note


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


def test_a_failed_probe_is_a_verdict_the_level_and_the_ones_below_are_not_reached(world):
    world.ladder["B2"] = "probe_failed"

    run = run_to_the_end(queue_production(world.source.id, ["B1", "B2"]))

    assert run.summary["levels"] == ["B2", "B1"]  # down the ladder, whatever order was asked
    # nobody is asked to read what the probe showed: the production finishes with its verdict
    assert run.status == "succeeded" and run.error == ""
    assert run.summary["outcomes"]["B2"] == {
        "outcome": "not reached",
        "reasons": ["The B2 probe failed: it says"],
    }
    assert run.summary["outcomes"]["B1"] == {
        "outcome": "not reached",
        "reasons": ["B2, the level above, was not reached."],
    }
    assert "book B2" not in world.calls


def test_a_level_the_ladder_remembers_as_not_reached_is_not_tried_again(world):
    world.ladder["B2"] = "not_reached"

    run = run_to_the_end(queue_production(world.source.id, ["B2"]))

    assert run.status == "succeeded"
    assert run.summary["outcomes"]["B2"]["reasons"] == [
        "B2 was tried before and not reached: it says"
    ]
    assert "probe B2" not in world.calls


def test_a_chapter_above_the_target_is_mended_by_paragraph_then_whole_then_the_level_is_dropped(
    world,
):
    world.above = [[2], [2], [2]]

    run = run_to_the_end(queue_production(world.source.id, ["B2", "B1"]))

    assert [call for call in world.calls if call.startswith(("paragraphs", "chapter"))] == [
        "paragraphs 2",
        "chapter 2",
    ]
    # every change sends the edition back to the judges before anything else looks at it
    assert world.calls.count("analysis") == 3
    # the book does not come down to B2: the edition goes, the ladder remembers, B1 is not tried
    assert run.status == "succeeded"
    reason = (
        "Chapter(s) 2 still read above B2 after the cited paragraphs and the whole chapter "
        "were each rewritten once."
    )
    assert run.summary["outcomes"]["B2"] == {"outcome": "not reached", "reasons": [reason]}
    assert world.dropped == [("B2", reason)]
    assert "purge book-b2" in world.calls
    assert run.summary["outcomes"]["B1"]["outcome"] == "not reached"
    assert "probe B1" not in world.calls


def test_a_few_chapters_one_level_above_are_rewritten_then_labelled_within_the_allowance(world):
    # Dubliners' B1: one chapter of sixteen read B2 by both judges after both rewrites
    world.above = [[2], [2], [2]]
    world.tolerated = [[], [], [2]]

    run = run_to_the_end(queue_production(world.source.id, ["B2"]))

    assert [call for call in world.calls if call.startswith(("paragraphs", "chapter"))] == [
        "paragraphs 2",
        "chapter 2",
    ]
    assert run.status == "succeeded"
    assert run.summary["outcomes"]["B2"]["outcome"] == "ready"
    notes = [entry["note"] for entry in run.summary["log"]]
    assert any(
        "Chapter(s) 2 read one level above B2" in note and "within the allowance" in note
        for note in notes
    )
    assert world.dropped == []


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
    run.summary["tracks"]["levels"]["since"] = (timezone.now() - timedelta(hours=4)).isoformat()
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
            "rights": {
                "status": "UNKNOWN",
                "explanation": "No death year for the author.",
                "countries": ["UA", "DE"],
                "catalog_title": "A Book",
                "catalog_author": "Author",
            },
        },
    )
    client.force_login(get_user_model().objects.create_user("staff", is_staff=True))

    page = client.get(reverse("catalog:edition-detail", args=[source.id])).content.decode()

    assert "Production of B2, B1" in page
    assert "B1 held: The B1 probe failed: too much is lost." in page
    assert (
        "Rights in UA, DE: <strong>unknown</strong> · catalogue: A Book by Author"
        " · No death year for the author."
    ) in page


def test_a_job_a_dead_worker_left_running_is_started_again_not_waited_for(world):
    world.audit = "running"
    world.audit_touched = timezone.now() - timedelta(hours=1)

    run = run_to_the_end(queue_production(world.source.id, ["B2"]))

    assert "audit" in world.calls and run.status == "succeeded"


@pytest.fixture
def translating(world, monkeypatch):
    """A world whose translator and editors finish when the test says so."""

    def create(*, source_edition, target_language, register, tier):
        world.calls.append(f"translation {target_language} {tier}")
        return Edition.objects.create(
            work=source_edition.work,
            source_edition=source_edition,
            slug=f"book-{target_language}",
            language=target_language,
            edition_type=Edition.EditionType.MACHINE_TRANSLATION,
            literary_register=register,
            status=Edition.Status.PROCESSING,
        )

    monkeypatch.setattr(f"{CATALOG}.ai_translation.create_parallel_translation", create)
    monkeypatch.setattr(f"{CATALOG}.translation_review.review_plan", lambda edition: {"hash": "h"})

    def written(language):
        edition = Edition.objects.get(slug=f"book-{language}")
        chapter = Chapter.objects.create(edition=edition, sequence=1, title="1")
        edition.blocks.create(
            chapter=chapter, sequence=1, block_id="c1.p1", block_type="paragraph", text="Текст."
        )
        edition.status = Edition.Status.REVIEW
        edition.save()
        return edition

    def reviewed(edition):
        PipelineRun.objects.create(
            edition=edition,
            stage=PipelineRun.Stage.TRANSLATE,
            processor_version="translation-review-v3",
            input_hash="h",
            idempotency_key=f"review-{edition.slug}",
            status=PipelineRun.Status.SUCCEEDED,
        )

    world.written, world.reviewed = written, reviewed
    return world


def test_a_language_is_translated_read_by_two_editors_corrected_and_signed_off(translating):
    world = translating
    world.findings = [finding(1, backed_by_both=True), finding(2, backed_by_both=False)]
    run = queue_production(world.source.id, [], languages=["UK", "uk"])
    assert run.summary["languages"] == ["uk"]

    assert not advance(run.id)  # being written
    edition = world.written("uk")
    assert not advance(run.id)  # with the editors
    world.reviewed(edition)
    run = run_to_the_end(run)

    assert world.calls == ["translation uk codex", "apply 1 carry=False by=None"]
    assert run.status == "succeeded" and run.summary["outcomes"]["uk"]["outcome"] == "ready"
    edition.refresh_from_db()
    assert edition.status == Edition.Status.READY
    # what one editor raised and the other refused stays open for a person and holds nothing
    assert [f.id for f in world.findings] == [2]


def test_a_serious_finding_both_editors_stand_behind_that_cannot_be_placed_holds_it(translating):
    world = translating
    world.findings = [finding(1, backed_by_both=True, can_apply=False)]
    run = queue_production(world.source.id, [], languages=["uk"])
    advance(run.id)
    edition = world.written("uk")
    advance(run.id)
    world.reviewed(edition)

    run = run_to_the_end(run)

    assert run.status == "failed"
    assert "1 serious finding(s) both editors stand behind could not be corrected" in run.error
    edition.refresh_from_db()
    assert edition.status == Edition.Status.REVIEW


def test_a_level_not_reached_does_not_stop_the_translations(translating):
    world = translating
    world.ladder["B2"] = "probe_failed"
    run = queue_production(world.source.id, ["B2", "B1"], languages=["uk"])
    advance(run.id)
    edition = world.written("uk")
    advance(run.id)
    world.reviewed(edition)

    run = run_to_the_end(run)

    outcomes = {target: o["outcome"] for target, o in run.summary["outcomes"].items()}
    assert outcomes == {"B2": "not reached", "B1": "not reached", "uk": "ready"}
    assert run.status == "succeeded" and run.error == ""


def test_a_level_the_book_already_reads_at_is_not_needed_and_the_rung_below_is_made(world):
    del world.ladder["B2"]  # the book itself is B2: its ladder starts at B1

    run = run_to_the_end(queue_production(world.source.id, ["B2", "B1"]))

    outcomes = {target: o["outcome"] for target, o in run.summary["outcomes"].items()}
    assert outcomes == {"B2": "not needed", "B1": "ready"}
    assert run.status == "succeeded" and "book B1" in world.calls


def test_a_source_the_judges_are_part_way_through_is_waited_for_not_started_again(world):
    source = str(world.source.id)
    # the reading shows "partial" while the judges work; the run is what says they are working
    world.analysis[source] = "partial"
    world.analysis_runs[source] = SimpleNamespace(status="running", updated_at=timezone.now())
    run = queue_production(world.source.id, ["B2"])

    for _ in range(5):
        assert not advance(run.id)

    assert "analysis" not in world.calls
    world.analysis[source] = "complete"
    assert run_to_the_end(run).status == "succeeded"


def test_a_serious_agreed_finding_with_no_replacement_has_its_paragraph_rewritten(world):
    world.audit = "running"
    run = queue_production(world.source.id, ["B2"])
    advance(run.id)  # the probe is running
    advance(run.id)  # written, read, and now with the auditors
    chapter = Chapter.objects.get(edition__slug="book-b2", sequence=1)
    world.audit = "current"
    world.findings = [
        finding(
            7, backed_by_both=True, can_apply=False, block=SimpleNamespace(chapter_id=chapter.id)
        )
    ]
    run = run_to_the_end(run)

    assert any(call.startswith("repair") for call in world.calls)
    assert run.status == "succeeded"
    # the paragraph is rewritten once; a finding on it that comes back is not rewritten again
    assert run.summary["repaired"]["B2"] == ["c1.p7"]
    assert chapter.edition.block_revisions.count() == 0  # the fake wrote nothing itself


def test_a_translation_is_made_beside_the_levels_not_after_them(translating):
    world = translating
    world.ladder["B2"] = "probing"
    run = queue_production(world.source.id, ["B2"], languages=["uk"])

    assert not advance(run.id)

    run.refresh_from_db()
    tracks = run.summary["tracks"]
    assert tracks["levels"]["step"] == "probe" and tracks["languages"]["step"] == "translate"
    assert world.calls == ["translation uk codex"]
    assert "uk" in run.summary["editions"]
    # the step that only waited is not asked again while the other track catches up
    assert run.summary["starts"] == {"translation uk": 1}


def test_productions_held_by_circumstance_are_started_again_and_the_rest_left_alone(world):
    from almonium_book_processor.catalog.production import VERSION, requeue_held

    def held(slug, error, minutes_ago=90):
        work = Work.objects.create(slug=f"held-{slug}", title=slug, author="Author")
        source = Edition.objects.create(work=work, slug=f"held-{slug}-en", language="en")
        return PipelineRun.objects.create(
            edition=source,
            stage=PipelineRun.Stage.ADAPT,
            processor_version=VERSION,
            status=PipelineRun.Status.FAILED,
            input_hash="",
            idempotency_key=f"{slug}:production",
            error=error,
            finished_at=timezone.now() - timedelta(minutes=minutes_ago),
            summary={"levels": ["B2", "B1"], "languages": [], "register": "", "sign_off": True},
        )

    held("counter", "B2 held: 'book B2' was started 2 times and did not finish.")
    allowance = held("allowance", "B2 held: Allowance used up: Codex returned no answer.")
    held("left", "Left behind: nothing worked on this job for over 2 hours.")
    fresh = held("fresh", "B2 held: Allowance used up: just now.", minutes_ago=5)
    book = held("book", "B1 held: Chapter(s) 2 still read above B1 after the rewrites.")

    only_allowance = requeue_held(allowance_only=True)
    assert [run.edition for run in only_allowance] == [allowance.edition]

    every = requeue_held()
    # the allowance hold's source now has a production under way, so it is not started twice
    assert sorted(run.edition.slug for run in every) == ["held-counter-en", "held-left-en"]
    assert all(run.summary["levels"] == ["B2", "B1"] for run in every)
    for untouched in (fresh, book):
        assert untouched.edition.pipeline_runs.filter(processor_version=VERSION).count() == 1
