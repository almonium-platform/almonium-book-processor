"""Keeping a long job's run visibly alive while one slow call runs.

A job is taken for dead when nothing has touched its run for a while (``production.STALL``,
``janitor.ABANDONED_AFTER``) and is started again beside it or closed. A job whose one call
to a model lasts longer than that is alive, and has to say so: on 24 October 2026 a fidelity
audit silent for half an hour over one chapter was started a second time and paid twice.
"""

from __future__ import annotations

import threading
from contextlib import contextmanager

from django.db import connection
from django.utils import timezone

from almonium_book_processor.catalog.models import PipelineRun


@contextmanager
def heartbeat(run_id, every: float = 60.0):
    """Touch the run's ``updated_at`` every ``every`` seconds while the block runs."""

    done = threading.Event()

    def beat() -> None:
        try:
            while not done.wait(every):
                PipelineRun.objects.filter(pk=run_id, status=PipelineRun.Status.RUNNING).update(
                    updated_at=timezone.now()
                )
        finally:
            # the thread opened its own database connection
            connection.close()

    thread = threading.Thread(target=beat, daemon=True)
    thread.start()
    try:
        yield
    finally:
        done.set()
        thread.join()
