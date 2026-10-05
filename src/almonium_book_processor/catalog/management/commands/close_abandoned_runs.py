from datetime import timedelta

from django.core.management.base import BaseCommand

from almonium_book_processor.catalog.janitor import abandoned_runs, close_abandoned_runs


class Command(BaseCommand):
    help = "Close jobs a stopped worker left queued or running; a worker does this when it starts."

    def add_arguments(self, parser):
        parser.add_argument("--hours", type=float, default=2.0)
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        after = timedelta(hours=options["hours"])
        for run in abandoned_runs(after).select_related("edition"):
            self.stdout.write(
                f"{run.edition.slug}  {run.stage}  {run.processor_version}  {run.status}  "
                f"untouched since {run.updated_at:%Y-%m-%d %H:%M}"
            )
        if not options["dry_run"]:
            self.stdout.write(f"Closed {close_abandoned_runs(after)} job(s).")
