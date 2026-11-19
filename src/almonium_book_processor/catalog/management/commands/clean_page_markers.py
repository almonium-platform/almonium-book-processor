from collections import Counter

from django.core.management.base import BaseCommand, CommandError

from almonium_book_processor.catalog.models import Edition
from almonium_book_processor.catalog.page_cleanup import apply_page_cleanup, plan_page_cleanup


class Command(BaseCommand):
    help = "Remove source-tagged inline printed page markers, retaining the original text."

    def add_arguments(self, parser):
        parser.add_argument("--work", help="Limit the scan to a work slug.")
        parser.add_argument("--apply", action="store_true", help="Apply and queue local jobs.")

    def handle(self, *args, work=None, apply=False, **options):
        edits, stats = plan_page_cleanup(work)
        editions = Edition.objects.filter(pk__in={edit.block.edition_id for edit in edits})
        works = dict(editions.values_list("pk", "work__slug"))
        for slug, count in sorted(Counter(works[edit.block.edition_id] for edit in edits).items()):
            self.stdout.write(f"{slug}: {count} blocks")
        stats["matched blocks"] = len(edits)
        stats["matched editions"] = len(works)
        if apply:
            try:
                stats.update(apply_page_cleanup(edits))
            except ValueError as error:
                raise CommandError(str(error)) from error
        for name, count in sorted(stats.items()):
            self.stdout.write(f"{name}: {count}")
