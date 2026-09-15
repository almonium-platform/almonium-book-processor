from django.core.management.base import BaseCommand

from almonium_book_processor.catalog.models import Edition
from almonium_book_processor.catalog.sentence_alignment import generate_sentence_preview


class Command(BaseCommand):
    help = "Queue paid sentence alignment for one public-library chapter (does not publish)."

    def add_arguments(self, parser):
        parser.add_argument("primary_slug")
        parser.add_argument("secondary_slug")
        parser.add_argument("chapter", type=int)
        parser.add_argument("--blocks", nargs="+")

    def handle(self, *args, **options):
        primary = Edition.objects.get(slug=options["primary_slug"])
        secondary = Edition.objects.get(slug=options["secondary_slug"])
        result = generate_sentence_preview.delay(
            str(primary.id), str(secondary.id), options["chapter"], options["blocks"]
        )
        self.stdout.write(f"Queued sentence preview: {result.id}")
