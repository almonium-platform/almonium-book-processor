"""Reader-safe chapter metadata. No provider calls or staff-only evidence."""

from almonium_book_processor.catalog.chapter_analysis import (
    analysis_context,
    current_chapter_hashes,
)


def retained_projections(edition) -> dict[str, tuple[dict, dict]]:
    """The latest complete difficulty and summary of each chapter, from any run.

    A text correction or a prompt change makes the whole run stale, but the
    description written for a chapter still describes that chapter. Readers
    keep it until a new run replaces it; the caller compares the chapter hash
    to say whether the chapter's own text has changed since.
    """
    from almonium_book_processor.catalog.chapter_projections import (
        DIFFICULTY_VERSION,
        KINDS,
        SUMMARY_VERSION,
    )

    difficulties: dict[str, dict] = {}
    for artifact in edition.artifacts.filter(
        kind=KINDS[0],
        chapter__isnull=False,
        processor_version=DIFFICULTY_VERSION,
        payload__complete=True,
    ).order_by("-created_at"):
        difficulties.setdefault(str(artifact.chapter_id), artifact.payload)
    summaries: dict[tuple, dict] = {}
    for artifact in edition.artifacts.filter(
        kind=KINDS[1],
        chapter__isnull=False,
        processor_version=SUMMARY_VERSION,
        payload__complete=True,
    ).order_by("-created_at"):
        key = (
            str(artifact.chapter_id),
            artifact.payload.get("chapter_hash"),
            artifact.payload.get("analysis_spec_hash"),
        )
        summaries.setdefault(key, artifact.payload)
    retained = {}
    for chapter_id, difficulty in difficulties.items():
        summary = summaries.get(
            (chapter_id, difficulty.get("chapter_hash"), difficulty.get("analysis_spec_hash"))
        )
        if summary:
            retained[chapter_id] = (difficulty, summary)
    return retained


def chapter_rows(edition) -> list[dict]:
    """Each chapter's reader-facing analysis, with the hashes it was made for."""

    context = analysis_context(edition)
    projections = {row["chapter"].id: row for row in context.get("chapter_projections", [])}
    state = context.get("projection_state", "pending")
    retained = hashes = None
    chapters = []
    for chapter in edition.chapters.order_by("sequence"):
        row = projections.get(chapter.id, {})
        difficulty = row.get("difficulty") or {}
        summary = row.get("summary") or {}
        status = "complete" if difficulty.get("complete") else state
        if not (difficulty.get("complete") and summary.get("complete")):
            if retained is None:
                retained = retained_projections(edition)
                hashes = current_chapter_hashes(edition)
            kept = retained.get(str(chapter.id))
            if kept:
                difficulty, summary = kept
                unchanged = difficulty.get("chapter_hash") == hashes.get(str(chapter.id))
                status = "complete" if unchanged else "stale"
        chapters.append(
            {
                "id": str(chapter.id),
                "sequence": chapter.sequence,
                "title": chapter.title,
                "analysisStatus": status,
                "cefrEstimate": difficulty.get("cefr_estimate")
                if difficulty.get("complete")
                else None,
                "descriptions": [
                    section["spoiler_free_description"] for section in summary.get("sections", [])
                ]
                if summary.get("complete")
                else [],
                "chapter_hash": summary.get("chapter_hash"),
                "analysis_spec_hash": summary.get("analysis_spec_hash"),
            }
        )
    return chapters


PUBLIC_KEYS = ("id", "sequence", "title", "analysisStatus", "cefrEstimate", "descriptions")


def public_chapters(edition):
    if edition.is_parallel_translation:
        return _translated_chapters(edition)
    return [{key: row[key] for key in PUBLIC_KEYS} for row in chapter_rows(edition)]


def _translated_chapters(edition):
    """A parallel translation's contents: the source's level, its own descriptions.

    The rubric is never applied to translated text, so the reading demand
    shown is the source's. A description appears only once it is translated
    from the source's current analysis; until then the chapter says so
    rather than showing the source language.
    """

    from almonium_book_processor.catalog.adaptation import digest
    from almonium_book_processor.catalog.metadata_translation import translated_summaries

    source_rows = {row["sequence"]: row for row in chapter_rows(edition.source_edition)}
    translated = translated_summaries(edition)
    chapters = []
    for chapter in edition.chapters.order_by("sequence"):
        row = source_rows.get(chapter.sequence)
        status, level, descriptions = "pending", None, []
        if row is not None:
            status, level = row["analysisStatus"], row["cefrEstimate"]
            summary = translated.get(row["id"])
            if (
                summary
                and row["descriptions"]
                and summary["chapter_hash"] == row["chapter_hash"]
                and summary["analysis_spec_hash"] == row["analysis_spec_hash"]
                and summary["source_descriptions_hash"] == digest(row["descriptions"])
            ):
                descriptions = summary["descriptions"]
            elif row["descriptions"]:
                status = "pending"
        chapters.append(
            {
                "id": str(chapter.id),
                "sequence": chapter.sequence,
                "title": chapter.title,
                "analysisStatus": status,
                "cefrEstimate": level,
                "descriptions": descriptions,
            }
        )
    return chapters
