"""Jobs a stopped worker left behind are closed, so that nothing shows as running for ever.

A worker that is restarted or dies takes its job with it. The run stays "running", or
"queued" if its message was lost, with nobody working on it: the page shows a job in
progress, buttons that start it again refuse, and nothing says anything is wrong. Runs of the
kinds below are worked on by one process from start to end and touch their row as they go, so
one that nobody has touched for hours is not slow, it is abandoned. It is marked failed with
that reason and can be started again the usual way.

Kinds that wait on someone else, a Batch at the provider or a promotion target, are left
alone: silence is what waiting looks like there. So is every job while the plans queue is
paused: the owner stops the workers taking from it when the plans' allowances are used up,
and the jobs waiting on it fall silent on purpose. On 24 October 2026 a sweep took that
silence for abandonment and failed thirty-nine books.
"""

from __future__ import annotations

import logging
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from almonium_book_processor.catalog.models import PipelineRun

logger = logging.getLogger(__name__)

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


def plans_paused(inspect=None) -> bool:
    """Whether the plans queue is paused: workers answer, and none of them takes from it.

    When no worker answers at all nothing is known, and the sweep goes on as before.
    """

    try:
        if inspect is None:
            from almonium_book_processor.config.celery import app

            inspect = app.control.inspect(timeout=2.0)
        queues = inspect.active_queues() or {}
    except Exception:  # the broker may be away; that is not a pause
        return False
    if not queues:
        return False
    return not any(
        queue.get("name") == settings.PLAN_QUEUE for taken in queues.values() for queue in taken
    )


def close_abandoned_runs(after: timedelta = ABANDONED_AFTER, *, paused: bool | None = None) -> int:
    """Mark every abandoned run failed, saying why; the number closed.

    Nothing is closed while the plans queue is paused (``paused``, found out when not given).
    """

    if paused is None:
        paused = plans_paused()
    if paused:
        silent = abandoned_runs(after).count()
        if silent:
            logger.warning("The plans queue is paused; %s silent job(s) left alone.", silent)
        return 0
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
