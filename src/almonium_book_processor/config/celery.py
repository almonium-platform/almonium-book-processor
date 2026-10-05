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
def _close_what_the_last_worker_left(**_) -> None:
    """A worker that starts closes the jobs a stopped one left behind (catalog/janitor.py)."""

    import logging

    try:
        from almonium_book_processor.catalog.janitor import close_abandoned_runs

        closed = close_abandoned_runs()
        if closed:
            logging.getLogger(__name__).warning("Closed %s abandoned job(s).", closed)
    except Exception:  # the worker must come up whatever the state of the ledger
        logging.getLogger(__name__).exception("Could not close abandoned jobs.")
