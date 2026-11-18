from django.core.management.base import BaseCommand, CommandError

from almonium_book_processor.catalog.image_cleanup import clean_image_text


class Command(BaseCommand):
    help = "Archive legacy image text as metadata and carry related results locally."

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply", action="store_true", help="Commit the cleanup; default is a preview."
        )
        parser.add_argument("--work", help="Limit the cleanup to a work slug.")

    def handle(self, *args, apply=False, work=None, **options):
        try:
            stats = clean_image_text(apply=apply, work=work)
        except ValueError as error:
            raise CommandError(str(error)) from error
        self.stdout.write("Applied" if apply else "Preview rolled back")
        for name, count in sorted(stats.items()):
            self.stdout.write(f"{name}: {count}")
