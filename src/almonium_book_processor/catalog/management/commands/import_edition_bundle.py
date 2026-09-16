"""Land an edition bundle from disk, the way the promotion endpoint does."""

from __future__ import annotations

from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from almonium_book_processor.catalog.promotion import (
    PromotionError,
    import_bundle,
    queue_publications,
)


class Command(BaseCommand):
    help = "Import a promotion bundle, replacing what an earlier promotion left here."

    def add_arguments(self, parser) -> None:
        parser.add_argument("path", help="The .zip bundle to import.")
        parser.add_argument(
            "--origin",
            default=None,
            help="Where the bundle came from; defaults to what the bundle says.",
        )
        parser.add_argument(
            "--publish",
            action="store_true",
            help="Queue this environment's publication of the carried editions afterwards.",
        )

    def handle(self, *args, **options) -> None:
        path = Path(options["path"])
        if not path.is_file():
            raise CommandError(f"{path} does not exist.")
        try:
            result = import_bundle(path.read_bytes(), origin=options["origin"])
        except PromotionError as error:
            raise CommandError(str(error)) from error
        self.stdout.write(
            f"Imported {', '.join(result['imported']) or 'nothing'}; "
            f"already current: {', '.join(result['skipped']) or 'nothing'}."
        )
        if options["publish"]:
            queued = queue_publications(result["imported"] + result["skipped"])
            self.stdout.write(f"Publication queued for {', '.join(queued) or 'nothing'}.")
