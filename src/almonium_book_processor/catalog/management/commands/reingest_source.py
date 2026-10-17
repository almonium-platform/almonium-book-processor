from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from almonium_book_processor.catalog.models import Edition
from almonium_book_processor.catalog.reingest import CannotReingest, reset_for_reingest
from almonium_book_processor.catalog.tasks import process_book_pipeline


class Command(BaseCommand):
    help = (
        "Rebuild a source ingest's chapters from the file it already downloaded: the editions "
        "made from it are purged, its pipeline runs dropped, and the download pipeline runs "
        "again on the stored file. Queued to the worker unless --inline runs it here."
    )

    def add_arguments(self, parser):
        parser.add_argument("slugs", nargs="+", help="edition slugs of source ingests")
        parser.add_argument(
            "--inline",
            action="store_true",
            help="run the pipeline in this process instead of queueing it to the worker",
        )

    def handle(self, *args, **options):
        editions = []
        for slug in options["slugs"]:
            try:
                editions.append(
                    Edition.objects.select_related("work", "source_download").get(slug=slug)
                )
            except Edition.DoesNotExist as error:
                raise CommandError(f"No edition is called {slug}.") from error

        for edition in editions:
            try:
                with transaction.atomic():
                    purged = reset_for_reingest(edition)
                    if not options["inline"]:
                        transaction.on_commit(
                            lambda edition_id=str(edition.id): process_book_pipeline.delay(
                                edition_id
                            )
                        )
            except CannotReingest as error:
                raise CommandError(str(error)) from error
            if purged:
                self.stdout.write(f"{edition.slug}: purged {', '.join(purged)}")
            if options["inline"]:
                process_book_pipeline.run(str(edition.id))
                edition.refresh_from_db()
                self.stdout.write(
                    f"{edition.slug}: rebuilt, {edition.chapters.count()} chapters, "
                    f"status {edition.status}"
                )
            else:
                self.stdout.write(f"{edition.slug}: pipeline queued")
