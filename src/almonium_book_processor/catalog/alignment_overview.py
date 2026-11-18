"""Dashboard statistics from the latest offline run for each edition pair."""

from collections import Counter

from almonium_book_processor.catalog.models import PipelineRun, Work
from almonium_book_processor.processing.sentence_correspondence import VERSION


def alignment_overview() -> dict:
    runs = (
        PipelineRun.objects.filter(
            stage=PipelineRun.Stage.ALIGN,
            summary__method=VERSION,
            edition__work__visibility=Work.Visibility.PUBLIC,
            edition__withdrawal_requested_at=None,
        )
        .order_by("-created_at", "-pk")
        .values_list("edition_id", "status", "summary")
    )
    seen = set()
    statuses = Counter()
    confirmed = uncertain = 0
    for edition, status, summary in runs:
        secondary = summary.get("secondary_id")
        if not secondary:
            continue
        pair = frozenset((str(edition), secondary))
        if pair in seen:
            continue
        seen.add(pair)
        statuses[status] += 1
        if status == PipelineRun.Status.SUCCEEDED:
            confirmed += summary.get("highlighted_groups", 0)
            uncertain += summary.get("uncertain_groups", 0)

    groups = confirmed + uncertain
    return {
        "version": VERSION.removeprefix("offline-sentence-"),
        "done": statuses[PipelineRun.Status.SUCCEEDED],
        "running": statuses[PipelineRun.Status.RUNNING],
        "queued": statuses[PipelineRun.Status.QUEUED],
        "failed": statuses[PipelineRun.Status.FAILED],
        "confirmed": confirmed,
        "uncertain": uncertain,
        "confirmed_percent": 100 * confirmed / groups if groups else None,
    }
