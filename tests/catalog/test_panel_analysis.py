"""Where judges are configured they are the chapter analysis: one judge of levels."""

import json
from datetime import timedelta

import pytest
from django.utils import timezone

from almonium_book_processor.catalog.chapter_analysis import (
    analysis_context,
    analyze_chapters,
    edition_spec,
    queue_analysis,
)
from almonium_book_processor.catalog.models import (
    Chapter,
    ContentBlock,
    Edition,
    PipelineRun,
    Work,
)

pytestmark = pytest.mark.django_db

JUDGES = "claude-code:claude-opus-5-5,codex:gpt-6.1-sol"


@pytest.fixture
def edition(settings, monkeypatch):
    settings.OPENAI_API_KEY = ""
    settings.DIFFICULTY_JUDGES = JUDGES
    settings.DIFFICULTY_READINGS = 3
    for task in ("analyze_edition_chapters", "project_chapter_analysis"):
        monkeypatch.setattr(f"almonium_book_processor.catalog.tasks.{task}.delay", lambda _: None)
    work = Work.objects.create(slug="judged", title="A book", author="Author")
    edition = Edition.objects.create(
        work=work,
        slug="judged-en",
        language="en",
        source_sha256="a" * 64,
        status=Edition.Status.READY,
    )
    for sequence in (1, 2):
        chapter = Chapter.objects.create(edition=edition, sequence=sequence, title=f"{sequence}")
        ContentBlock.objects.create(
            edition=edition,
            chapter=chapter,
            sequence=1,
            block_id=f"c{sequence}.p1",
            block_type="paragraph",
            text="Ere dawn, the traveler considered the journey.",
        )
    return edition


class Judges:
    """Each model answers every window with its own level, and signs its description."""

    def __init__(self, levels):
        self.levels = levels
        self.bodies = []

    def respond(self, body):
        self.bodies.append(body)
        block = json.loads(body["input"])["blocks"][0]["block_id"]
        result = {
            "cefr_estimate": self.levels[body["model"]],
            "confidence": 0.75,
            "archaism_score": 0.3,
            "modernisation_would_help": False,
            "evidence": [
                {
                    "block_id": block,
                    "quote": "Ere",
                    "dimension": "archaism",
                    "explanation": "An obsolete conjunction.",
                }
            ],
            "spoiler_free_description": f"A traveler considers a journey, says {body['model']}.",
            "recap": "The traveler reflects before dawn.",
            "hard_words": [],
            "themes": ["Travel"],
            "characters": ["The traveler"],
            "setting": "Before dawn",
            "content_flags": [],
        }
        return {
            "status": "completed",
            "usage": {"input_tokens": 1000, "output_tokens": 100},
            "output": [
                {
                    "type": "message",
                    "content": [{"type": "output_text", "text": json.dumps(result)}],
                }
            ],
        }


def test_the_judges_read_an_original_once_each_by_the_whole_rubric_and_theirs_is_its_level(
    edition,
):
    judges = Judges({"claude-opus-5-5": "B2", "gpt-6.1-sol": "C1"})

    run = queue_analysis(str(edition.id))
    analyze_chapters(str(run.id), provider=judges)

    # two chapters, two judges, one reading each; nobody is told to rate the wording alone
    assert sorted(body["model"] for body in judges.bodies) == [
        "claude-opus-5-5",
        "claude-opus-5-5",
        "gpt-6.1-sol",
        "gpt-6.1-sol",
    ]
    assert not any("WORDING ONLY" in body["instructions"] for body in judges.bodies)
    run.refresh_from_db()
    assert run.status == "succeeded"
    assert run.summary["spec"]["model"] == "claude-opus-5-5 + gpt-6.1-sol"
    context = analysis_context(edition)
    assert context["projection_state"] == "complete"
    # the strictest judge decides the level, and its reading describes the chapter
    for row in context["chapter_projections"]:
        assert row["difficulty"]["max_level"] == "C1"
        assert row["difficulty"]["judges"] == [
            {"model": "claude-opus-5-5", "level": "B2", "readings": ["B2"]},
            {"model": "gpt-6.1-sol", "level": "C1", "readings": ["C1"]},
        ]
        assert "says gpt-6.1-sol" in row["summary"]["sections"][0]["spoiler_free_description"]
    edition.refresh_from_db()
    assert (edition.cefr_level, edition.cefr_level_source) == ("C1", Edition.LevelSource.ANALYSIS)
    # the text as it stands is read once: asking again costs nothing
    analyze_chapters(str(queue_analysis(str(edition.id)).id), provider=judges)
    assert len(judges.bodies) == 4


def test_the_judges_read_an_adaptation_for_its_wording_and_are_not_asked_twice(
    edition,
):
    from almonium_book_processor.catalog.adaptation_wording import check_edition

    edition.edition_type = Edition.EditionType.ADAPTATION
    edition.save()
    edition.blocks.update(attributes={"adaptation": {"target_level": "B1"}})
    judges = Judges({"claude-opus-5-5": "B1", "gpt-6.1-sol": "B1"})

    # the level check reads first, as the command and the mending steps do; the judges'
    # first readings agree on both chapters, so neither reads a second time
    check_edition(edition, provider=judges)
    assert len(judges.bodies) == 2 * 2
    assert all("WORDING ONLY" in body["instructions"] for body in judges.bodies)

    run = queue_analysis(str(edition.id))
    assert run.summary["spec"]["readings"] == 3
    analyze_chapters(str(run.id), provider=judges)

    # the analysis is those same readings: no chapter is read again
    assert len(judges.bodies) == 4
    context = analysis_context(edition)
    assert context["projection_state"] == "complete"
    assert [row["difficulty"]["max_level"] for row in context["chapter_projections"]] == [
        "B1",
        "B1",
    ]


def test_without_judges_the_single_model_is_the_analysis(edition, settings):
    settings.DIFFICULTY_JUDGES = ""

    spec = edition_spec(edition)

    assert "panel" not in spec and spec["provider"] == "openai"


def test_a_reading_left_running_by_a_worker_that_died_is_taken_up_again(edition):
    from almonium_book_processor.catalog.adaptation_wording import judge_verdicts

    chapter = edition.chapters.get(sequence=1)

    class Dies(Judges):
        def respond(self, body):
            raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        judge_verdicts(edition, chapter, provider=Dies({}))
    reading = PipelineRun.objects.get(processor_version="adaptation-wording-v1")
    PipelineRun.objects.filter(pk=reading.pk).update(status=PipelineRun.Status.RUNNING)
    judges = Judges({"claude-opus-5-5": "B2", "gpt-6.1-sol": "B2"})

    # a reading someone is still making is left alone
    with pytest.raises(ValueError, match="already running"):
        judge_verdicts(edition, chapter, provider=judges)
    PipelineRun.objects.filter(pk=reading.pk).update(updated_at=timezone.now() - timedelta(hours=1))

    assert [v["max_level"] for v in judge_verdicts(edition, chapter, provider=judges)] == [
        "B2",
        "B2",
    ]


def test_the_estimate_counts_every_judge_and_every_reading_of_what_is_unread(edition):
    from almonium_book_processor.catalog.estimates import chapter_analysis

    before = chapter_analysis(edition)
    assert before.usd > 0 and "2 chapters for claude-opus-5-5 + gpt-6.1-sol" in before.note

    judges = Judges({"claude-opus-5-5": "B2", "gpt-6.1-sol": "B2"})
    analyze_chapters(str(queue_analysis(str(edition.id)).id), provider=judges)

    after = chapter_analysis(edition)
    assert after.usd == 0 and "reused" in after.note


def _adaptation_of(edition, chapters: int):
    edition.edition_type = Edition.EditionType.ADAPTATION
    edition.save()
    for sequence in range(3, chapters + 1):
        chapter = Chapter.objects.create(edition=edition, sequence=sequence, title=f"{sequence}")
        ContentBlock.objects.create(
            edition=edition,
            chapter=chapter,
            sequence=1,
            block_id=f"c{sequence}.p1",
            block_type="paragraph",
            text="Ere dawn, the traveler considered the journey.",
        )
    edition.blocks.update(attributes={"adaptation": {"target_level": "B1"}})


class ByChapter(Judges):
    """A judge reads the chapters named for it one level higher."""

    def __init__(self, harder: dict[str, set[int]]):
        super().__init__({})
        self.harder = harder

    def respond(self, body):
        sequence = json.loads(body["input"])["chapter_sequence"]
        self.levels = {body["model"]: "B2" if sequence in self.harder[body["model"]] else "B1"}
        return super().respond(body)


def test_one_chapter_in_ten_may_read_a_level_higher_when_the_judges_disagree(edition, settings):
    from almonium_book_processor.catalog.adaptation_quality import adaptation_quality

    settings.DIFFICULTY_READINGS = 1
    _adaptation_of(edition, 10)
    # one judge reads chapter 10 a level above the target, the other reads it at the target
    judges = ByChapter({"claude-opus-5-5": set(), "gpt-6.1-sol": {10}})
    analyze_chapters(str(queue_analysis(str(edition.id)).id), provider=judges)

    quality = adaptation_quality(edition)

    assert quality["adaptation_blocker"] == ""
    assert quality["adaptation_split_chapters"] == [10]
    assert quality["adaptation_above_chapters"] == []


def test_one_chapter_both_judges_read_above_the_target_is_above_but_within_the_allowance(
    edition, settings
):
    from almonium_book_processor.catalog.adaptation_quality import adaptation_quality

    settings.DIFFICULTY_READINGS = 1
    _adaptation_of(edition, 10)
    judges = ByChapter({"claude-opus-5-5": {10}, "gpt-6.1-sol": {10}})
    analyze_chapters(str(queue_analysis(str(edition.id)).id), provider=judges)

    quality = adaptation_quality(edition)

    # the adapter still gets its tries at chapter 10 (production); the gate does not hold on it
    assert quality["adaptation_above_chapters"] == [10]
    assert quality["adaptation_tolerated_chapters"] == [10]
    assert quality["adaptation_blocker"] == ""


def test_more_chapters_above_the_target_than_the_allowance_hold_the_book(edition, settings):
    from almonium_book_processor.catalog.adaptation_quality import adaptation_quality

    settings.DIFFICULTY_READINGS = 1
    _adaptation_of(edition, 10)
    judges = ByChapter({"claude-opus-5-5": {8, 9, 10}, "gpt-6.1-sol": {8, 9, 10}})
    analyze_chapters(str(queue_analysis(str(edition.id)).id), provider=judges)

    quality = adaptation_quality(edition)

    assert quality["adaptation_above_chapters"] == [8, 9, 10]
    assert quality["adaptation_tolerated_chapters"] == []
    assert "Target B1 not achieved" in quality["adaptation_blocker"]


def test_more_disputed_chapters_than_the_allowance_all_hold_the_book(edition, settings):
    from almonium_book_processor.catalog.adaptation_quality import adaptation_quality

    settings.DIFFICULTY_READINGS = 1
    _adaptation_of(edition, 10)
    judges = ByChapter({"claude-opus-5-5": set(), "gpt-6.1-sol": {9, 10}})
    analyze_chapters(str(queue_analysis(str(edition.id)).id), provider=judges)

    quality = adaptation_quality(edition)

    assert quality["adaptation_above_chapters"] == [9, 10]
    assert quality["adaptation_split_chapters"] == []


def test_a_cancelled_analysis_is_not_started_again_by_its_old_message(edition):
    judges = Judges({"claude-opus-5-5": "B2", "gpt-6.1-sol": "B2"})
    run = queue_analysis(str(edition.id))
    PipelineRun.objects.filter(pk=run.pk).update(status=PipelineRun.Status.CANCELLED)

    analyze_chapters(str(run.id), provider=judges)

    assert judges.bodies == []
    # asked for again, it is queued and read
    analyze_chapters(str(queue_analysis(str(edition.id)).id), provider=judges)
    assert len(judges.bodies) == 4


def test_a_chapter_the_judges_disagree_about_is_read_three_times_by_each(edition, settings):
    from almonium_book_processor.catalog.adaptation_wording import check_chapter, wording_judges

    _adaptation_of(edition, 2)
    judges = ByChapter({"claude-opus-5-5": set(), "gpt-6.1-sol": {2}})

    for chapter in edition.chapters.order_by("sequence"):
        check_chapter(edition, chapter, provider=judges)

    # chapter 1: one reading each. Chapter 2: the first readings differ, so each judge reads
    # twice more, and its first reading is not paid for again.
    assert len(judges.bodies) == 2 + 2 + 4
    read = wording_judges(edition)
    assert sorted(read.values()) == [
        [("claude-opus-5-5", "B1"), ("gpt-6.1-sol", "B1")],
        [("claude-opus-5-5", "B1"), ("gpt-6.1-sol", "B2")],
    ]
    # asked again, nobody reads anything
    for chapter in edition.chapters.order_by("sequence"):
        check_chapter(edition, chapter, provider=judges)
    assert len(judges.bodies) == 8
