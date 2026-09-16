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


def public_chapters(edition):
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
            }
        )
    return chapters
