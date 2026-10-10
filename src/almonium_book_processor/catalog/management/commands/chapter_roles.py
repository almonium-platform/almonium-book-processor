from django.core.management.base import BaseCommand

from almonium_book_processor.catalog.front_matter import retag
from almonium_book_processor.catalog.models import Edition


class Command(BaseCommand):
    help = (
        "Tag every edition's chapters as front matter, story or back matter from their titles, "
        "as ingest does; editions made from a source copy the source's roles."
    )

    def handle(self, *args, **options):
        # sources first: their editions copy them
        editions = Edition.objects.order_by("source_edition_id", "slug")
        for edition in sorted(editions, key=lambda e: e.source_edition_id is not None):
            changed = retag(edition)
            if changed:
                self.stdout.write(f"{edition.slug}: {changed} chapter(s) retagged")
