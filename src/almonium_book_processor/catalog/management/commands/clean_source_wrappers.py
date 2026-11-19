from django.core.management.base import BaseCommand, CommandError

from almonium_book_processor.catalog.models import Edition
from almonium_book_processor.catalog.source_wrapper_cleanup import (
    apply_source_wrappers,
    plan_source_wrappers,
)


class Command(BaseCommand):
    help = "Archive verified digital wrapper blocks and merge false print-page chapters."

    def add_arguments(self, parser):
        parser.add_argument("--work", help="Limit the scan to a work slug.")
        parser.add_argument(
            "--apply", action="store_true", help="Apply the cleanup and queue local jobs."
        )

    def handle(self, *args, work=None, apply=False, **options):
        targets, counts = plan_source_wrappers(work)
        for pk, slug in (
            Edition.objects.filter(pk__in=targets).order_by("slug").values_list("pk", "slug")
        ):
            self.stdout.write(f"{slug}: {len(targets[pk])} blocks")
        if apply:
            try:
                counts.update(apply_source_wrappers(targets))
            except ValueError as error:
                raise CommandError(str(error)) from error
        for name, count in sorted(counts.items()):
            self.stdout.write(f"{name}: {count}")
