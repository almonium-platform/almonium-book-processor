from __future__ import annotations

import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "almonium_book_processor.config.settings")

app = Celery("almonium_book_processor")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()
