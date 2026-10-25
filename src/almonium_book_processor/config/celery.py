from __future__ import annotations

import os

from celery import Celery
from celery.signals import worker_ready

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "almonium_book_processor.config.settings")

app = Celery("almonium_book_processor")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()
app.conf.imports = ("almonium_book_processor.catalog.sentence_alignment",)


@worker_ready.connect
def _close_what_the_last_worker_left(sender=None, **_) -> None:
    """A plans worker that starts closes the jobs a stopped one left behind (catalog/janitor.py).

    Only a worker that takes from the plans queue sweeps: the jobs the sweep closes run
    there, and a container worker rebuilt after a code change knows nothing about them.
    """

    import logging

    try:
        from django.conf import settings

        from almonium_book_processor.catalog.janitor import close_abandoned_runs

        taken = getattr(getattr(sender, "task_consumer", None), "queues", None) or []
        if not any(getattr(queue, "name", None) == settings.PLAN_QUEUE for queue in taken):
            return
        from almonium_book_processor.catalog.plan_pause import stop_if_paused

        # the worker says which accounts it works on; a paused account keeps it standing still
        stop_if_paused(sender, getattr(sender, "hostname", "") or "")
        closed = close_abandoned_runs()
        if closed:
            logging.getLogger(__name__).warning("Closed %s abandoned job(s).", closed)
    except Exception:  # the worker must come up whatever the state of the ledger
        logging.getLogger(__name__).exception("Could not close abandoned jobs.")
