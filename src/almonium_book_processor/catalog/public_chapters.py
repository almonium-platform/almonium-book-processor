"""Reader-safe chapter metadata. No provider calls or staff-only evidence."""

from almonium_book_processor.catalog.chapter_analysis import analysis_context


def public_chapters(edition):
    context = analysis_context(edition)
    projections = {row["chapter"].id: row for row in context.get("chapter_projections", [])}
    chapters = []
    for chapter in edition.chapters.order_by("sequence"):
        row = projections.get(chapter.id, {})
        difficulty = row.get("difficulty") or {}
        summary = row.get("summary") or {}
        complete = difficulty.get("complete", False)
        chapters.append(
            {
                "id": str(chapter.id),
                "sequence": chapter.sequence,
                "title": chapter.title,
                "analysisStatus": "complete"
                if complete
                else context.get("projection_state", "pending"),
                "cefrEstimate": difficulty.get("cefr_estimate") if complete else None,
                "descriptions": [
                    section["spoiler_free_description"] for section in summary.get("sections", [])
                ]
                if summary.get("complete")
                else [],
            }
        )
    return chapters
