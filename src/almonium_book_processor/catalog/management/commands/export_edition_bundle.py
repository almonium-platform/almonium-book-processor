"""Write an edition bundle to disk, for a transfer the admin page cannot make."""

from __future__ import annotations

from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from almonium_book_processor.catalog.models import Edition
from almonium_book_processor.catalog.promotion import (
    PromotionError,
    bundle_hash,
    export_bundle,
    promotion_chain,
)


class Command(BaseCommand):
    help = "Export an edition and the editions it was generated from as a promotion bundle."

    def add_arguments(self, parser) -> None:
        parser.add_argument("slug", help="The edition slug to export.")
        parser.add_argument("path", help="Where to write the .zip bundle.")

    def handle(self, *args, **options) -> None:
        try:
            edition = Edition.objects.select_related("work", "source_edition").get(
                slug=options["slug"]
            )
        except Edition.DoesNotExist as error:
            raise CommandError(f"No edition with slug {options['slug']}.") from error
        try:
            bundle = export_bundle(edition)
        except PromotionError as error:
            raise CommandError(str(error)) from error
        path = Path(options["path"])
        path.write_bytes(bundle)
        slugs = ", ".join(item.slug for item in promotion_chain(edition))
        self.stdout.write(
            f"Wrote {path} ({len(bundle)} bytes, {bundle_hash(bundle)[:12]}) carrying {slugs}."
        )
