"""The plan jobs a worker is running now, one per line; nothing when none is.

``plan-service restart`` asks before it kills the workers: a restart cuts every call in
flight and leaves its run running for ever (see docs/RUNBOOK.md).
"""

from __future__ import annotations

from django.core.management.base import BaseCommand
from django.utils import timezone

from almonium_book_processor.catalog.janitor import WORKED_BY_ONE_PROCESS, abandoned_after
from almonium_book_processor.catalog.models import PipelineRun


class Command(BaseCommand):
    help = "List the jobs a plan worker is running now; silent when there are none."

    def handle(self, *args, **options):
        silent_after = timezone.now() - abandoned_after()
        from almonium_book_processor.catalog.production import VERSION

        # a production is a ticker, not a call in flight: between ticks a restart costs it
        # nothing, and while the queue is paused it is "running" with nobody working on it
        live = (
            PipelineRun.objects.filter(
                stage__in=WORKED_BY_ONE_PROCESS,
                status=PipelineRun.Status.RUNNING,
                updated_at__gte=silent_after,
            )
            .exclude(processor_version=VERSION)
            .select_related("edition")
            .order_by("stage", "updated_at")
        )
        for run in live:
            ago = int((timezone.now() - run.updated_at).total_seconds() // 60)
            self.stdout.write(
                f"{run.get_stage_display()} · {run.processor_version} · {run.edition.slug}"
                f" · touched {ago} min ago"
            )
