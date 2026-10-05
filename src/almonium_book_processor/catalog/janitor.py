"""Jobs a stopped worker left behind are closed, so that nothing shows as running for ever.

A worker that is restarted or dies takes its job with it. The run stays "running", or
"queued" if its message was lost, with nobody working on it: the page shows a job in
progress, buttons that start it again refuse, and nothing says anything is wrong. Runs of the
kinds below are worked on by one process from start to end and touch their row as they go, so
one that nobody has touched for hours is not slow, it is abandoned. It is marked failed with
that reason and can be started again the usual way.

Kinds that wait on someone else, a Batch at the provider or a promotion target, are left
alone: silence is what waiting looks like there.
"""

from __future__ import annotations

from datetime import timedelta

from django.utils import timezone

from almonium_book_processor.catalog.models import PipelineRun

# The longest a healthy job of these kinds is silent is one model call tried twice, an hour.
ABANDONED_AFTER = timedelta(hours=2)
WORKED_BY_ONE_PROCESS = (
    PipelineRun.Stage.TRANSLATE_METADATA,
    PipelineRun.Stage.CHAPTER_ANALYSIS,
    PipelineRun.Stage.ADAPT,
    PipelineRun.Stage.GLOSSES,
    PipelineRun.Stage.LEXICAL,
    PipelineRun.Stage.SENTENCES,
    PipelineRun.Stage.SOURCE_QA,
)


def abandoned_runs(after: timedelta = ABANDONED_AFTER):
    return PipelineRun.objects.filter(
        stage__in=WORKED_BY_ONE_PROCESS,
        status__in=[PipelineRun.Status.QUEUED, PipelineRun.Status.RUNNING],
        updated_at__lt=timezone.now() - after,
    )


def close_abandoned_runs(after: timedelta = ABANDONED_AFTER) -> int:
    """Mark every abandoned run failed, saying why; the number closed."""

    hours = int(after.total_seconds() // 3600)
    return abandoned_runs(after).update(
        status=PipelineRun.Status.FAILED,
        error=(
            f"Left behind: nothing worked on this job for over {hours} hours, most likely "
            "because its worker was restarted. Start it again."
        ),
        finished_at=timezone.now(),
        updated_at=timezone.now(),
    )
