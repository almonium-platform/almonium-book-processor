"""The wording level of an adapted edition's chapters, as the pilot's judges read it.

A level on an adaptation promises its wording. The chapter analysis every edition gets rates
reading demand as a whole, with the library's single judge; a pilot is judged for wording by
the panel in ``pilot_difficulty``. A whole adaptation is held to the level its probe passed
at, so it is read by the same judges, chapter by chapter, and their level is what the
adaptation's gate uses for every chapter whose current text they have read.

A chapter they read above the target goes back to the adapter once with what they cited,
the way a probe's chapter does; the revision is applied only if the judges put it at the
target.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from django.db import connection

from almonium_book_processor.catalog.chapter_analysis import _hash, chapter_blocks
from almonium_book_processor.catalog.chapter_projections import LEVELS
from almonium_book_processor.catalog.models import Chapter, Edition, PipelineRun
from almonium_book_processor.catalog.pilot_difficulty import (
    judge_readings,
    judge_specs,
    judge_text,
    panel_verdict,
)

WORDING_VERSION = "adaptation-wording-v1"


def text_hash(blocks: list[dict]) -> str:
    return _hash([[block["block_id"], block["text"]] for block in blocks])


def check_chapter(edition: Edition, chapter: Chapter, *, provider=None) -> dict | None:
    """The panel's reading of one chapter's current text; a text already read is not read again."""

    blocks = chapter_blocks(chapter)
    if not blocks:
        return None
    digest = text_hash(blocks)
    readings = judge_readings()
    verdicts = [
        judge_text(
            edition=edition,
            key=f"{chapter.id}:wording",
            seed=digest,
            summary={"chapter_id": str(chapter.id), "text_hash": digest, "readings": readings},
            chapter_sequence=chapter.sequence,
            blocks=blocks,
            spec=spec,
            readings=readings,
            provider=provider,
            processor_version=WORDING_VERSION,
        )
        for spec in judge_specs(edition.language)
    ]
    return panel_verdict(verdicts, edition.language, readings)


def check_edition(edition: Edition, *, provider=None, workers: int = 1) -> dict[str, dict]:
    """Every chapter's wording level, by chapter id. ``workers`` chapters are read at a time."""

    chapters = list(edition.chapters.order_by("sequence").prefetch_related("blocks"))

    def read(chapter: Chapter):
        return check_chapter(edition, chapter, provider=provider)

    def in_thread(chapter: Chapter):
        try:
            return read(chapter)
        finally:
            # each thread opened its own database connection
            connection.close()

    with ThreadPoolExecutor(max_workers=max(workers, 1)) as pool:
        verdicts = list(pool.map(in_thread, chapters) if workers > 1 else map(read, chapters))
    return {str(c.id): v for c, v in zip(chapters, verdicts, strict=True) if v is not None}


def wording_levels(edition: Edition) -> dict[str, str]:
    """The panel's level of each chapter whose current text every judge configured has read."""

    specs = judge_specs(edition.language)
    readings = judge_readings()
    read: dict[tuple[str, str], list[tuple[dict, str]]] = {}
    for run in edition.pipeline_runs.filter(
        processor_version=WORDING_VERSION, status=PipelineRun.Status.SUCCEEDED
    ):
        summary = run.summary
        if summary.get("readings") != readings:
            continue
        read.setdefault((summary["chapter_id"], summary["text_hash"]), []).append(
            (summary["spec"], summary["assessment"]["max_level"])
        )
    if not read:
        return {}
    levels = {}
    for chapter in edition.chapters.prefetch_related("blocks"):
        blocks = chapter_blocks(chapter)
        if not blocks:
            continue
        seen = read.get((str(chapter.id), text_hash(blocks)), [])
        found = [level for spec in specs for seen_spec, level in seen if seen_spec == spec]
        if len(found) == len(specs):
            levels[str(chapter.id)] = max(found, key=LEVELS.index)
    return levels


AUTOMATIC_NOTE = (
    "Applied automatically. The level judges read the first draft of this chapter at {first}, "
    "above the target; the adapter revised it with what they cited and they read the revision "
    "at {level}. No person has reviewed this chapter for fidelity; the edition's fidelity "
    "audit reads it with the rest."
)


def revise_chapter(
    edition: Edition, chapter: Chapter, verdict: dict, *, provider=None, judge=None
) -> dict:
    """Send a chapter read above the target back to the adapter once, with what was cited.

    The revision is a whole-chapter pilot from the source, judged like any pilot, and is
    applied to the edition only when every judge puts it at the target. Says what happened.
    """

    from almonium_book_processor.catalog.adaptation import queue_pilot, run_pilot
    from almonium_book_processor.catalog.adaptation_floor import level_feedback
    from almonium_book_processor.catalog.adaptation_quality import adaptation_target
    from almonium_book_processor.catalog.pilot_application import apply_pilot, chapter_revision
    from almonium_book_processor.catalog.pilot_difficulty import assess_pilot

    target = adaptation_target(edition)
    source = edition.source_edition
    try:
        pilot = queue_pilot(
            source.id,
            source.chapters.get(sequence=chapter.sequence).id,
            target_level=target,
            dispatch=False,
            editorial_feedback=level_feedback(verdict, target),
        )
    except ValueError as error:
        # a chapter too long for one pilot cannot be revised whole
        return {"applied": False, "reason": str(error)}
    if pilot.status == PipelineRun.Status.QUEUED:
        run_pilot(pilot.id, provider=provider)
    pilot.refresh_from_db()
    if pilot.status != PipelineRun.Status.SUCCEEDED:
        return {"applied": False, "reason": f"generation {pilot.status}", "pilot_id": str(pilot.id)}
    assessment = assess_pilot(pilot.id, provider=judge)
    if LEVELS.index(assessment["max_level"]) > LEVELS.index(target):
        return {
            "applied": False,
            "reason": f"the revision was read at {assessment['max_level']}",
            "pilot_id": str(pilot.id),
        }
    apply_pilot(
        pilot_id=pilot.id,
        target_id=edition.id,
        expected_revision=chapter_revision(chapter),
        editor=None,
        notes=AUTOMATIC_NOTE.format(first=verdict["max_level"], level=assessment["max_level"]),
    )
    return {"applied": True, "level": assessment["max_level"], "pilot_id": str(pilot.id)}
