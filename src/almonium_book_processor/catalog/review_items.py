"""Turn open QA warnings into review cards that point at the content to inspect."""

import re
import uuid

from django.urls import reverse

from almonium_book_processor.catalog.models import Edition, PipelineRun, QAWarning

FIDELITY_CODE = "adaptation_fidelity_review"
CHAPTER_REPLACED_CODE = "adaptation_chapter_replaced"
DIFFICULTY_CODE = "adaptation_difficulty_gate"
TITLE_PAGE_CODE = "translation_title_page"

_UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")

GUIDANCE = {
    FIDELITY_CODE: (
        "Run the fidelity audit below, then read a sample of chapters side by side with "
        "the source. Resolve only if the adaptation keeps the events, claims and voice "
        "you would put your name to; the audit's findings are leads, not a certificate."
    ),
    CHAPTER_REPLACED_CODE: (
        "A reviewed chapter pilot overwrote this chapter. Read the chapter beside the "
        "source with word changes shown and check the listed corrections; each one is an "
        "audited text revision below."
    ),
    DIFFICULTY_CODE: (
        "Current chapter estimates are above target. Revise the cited passages or the "
        "assessment; this item clears itself when a reassessment passes."
    ),
    TITLE_PAGE_CODE: (
        "A translated edition is catalogued under the title, author and blurb a reader of "
        "its language knows. Run the metadata translation again, or enter them in the "
        "metadata form and confirm it; this item clears itself when a run succeeds."
    ),
}


def _reader_url(
    edition: Edition, chapter: int | None = None, block=None, *, changes: bool = False
) -> str:
    url = reverse("catalog:edition-reader", args=[edition.id])
    params = []
    if chapter is not None:
        params.append(f"chapter={chapter}")
    if edition.source_edition_id and edition.supports_parallel_reading:
        params.append(f"parallel={edition.source_edition_id}")
        if changes and edition.source_edition.language == edition.language:
            params.append("diff=1")
    if params:
        url += "?" + "&".join(params)
    if block is not None:
        url += f"#block-{block.id}"
    return url


def _pilot_run(edition: Edition, warning: QAWarning) -> PipelineRun | None:
    if warning.pipeline_run_id:
        return warning.pipeline_run
    # Older warnings only mention the pilot id in their text.
    for candidate in _UUID.findall(warning.message):
        run = PipelineRun.objects.filter(id=uuid.UUID(candidate)).first()
        if run is not None and run.summary.get("chapter_id"):
            return run
    return None


def _replaced_chapter(edition: Edition, run: PipelineRun | None) -> tuple[int, str] | None:
    """Sequence and display title of the chapter a pilot replaced in ``edition``."""

    if run is None or not run.summary.get("chapter_id"):
        return None
    source_chapter = run.edition.chapters.filter(id=run.summary["chapter_id"]).first()
    if source_chapter is None:
        return None
    # Adapted editions mirror the source chapter order.
    chapter = edition.chapters.filter(sequence=source_chapter.sequence).first()
    if chapter is None:
        return None
    title = chapter.title or source_chapter.title or f"chapter {chapter.sequence}"
    return chapter.sequence, title


def review_item(edition: Edition, warning: QAWarning) -> dict:
    """Describe where a staff reviewer should look before resolving ``warning``."""

    item = {
        "warning": warning,
        "guidance": GUIDANCE.get(warning.code, ""),
        "links": [],
    }
    if warning.block_id:
        block = warning.block
        item["links"].append(
            {
                "label": f"Open block {block.block_id}",
                "url": _reader_url(
                    edition, block.chapter.sequence if block.chapter else None, block
                ),
            }
        )
    if warning.code == CHAPTER_REPLACED_CODE:
        replaced = _replaced_chapter(edition, _pilot_run(edition, warning))
        if replaced is not None:
            sequence, title = replaced
            item["links"].append(
                {
                    "label": f"Read {title} beside the source",
                    "url": _reader_url(edition, sequence, changes=True),
                }
            )
        item["links"].append({"label": "Text corrections", "url": "#text-corrections"})
    elif warning.code == FIDELITY_CODE:
        item["links"].append(
            {"label": "Read beside the source", "url": _reader_url(edition, 1, changes=True)}
        )
        if edition.supports_parallel_reading and edition.source_edition_id:
            item["links"].append(
                {
                    "label": "Paired review workspace",
                    "url": reverse("catalog:alignment-review", args=[edition.id]),
                }
            )
    elif warning.code == DIFFICULTY_CODE:
        item["links"].append({"label": "Chapter estimates", "url": "#chapter-analysis"})
    elif warning.code == TITLE_PAGE_CODE:
        item["links"].append({"label": "Metadata translation", "url": "#metadata-translation"})
        item["links"].append({"label": "Metadata form", "url": "#metadata"})
    return item


def review_items(edition: Edition) -> list[dict]:
    return [
        review_item(edition, warning)
        for warning in edition.warnings.select_related("block__chapter", "pipeline_run__edition")
        if warning.severity != QAWarning.Severity.INFO and warning.resolved_at is None
    ]
