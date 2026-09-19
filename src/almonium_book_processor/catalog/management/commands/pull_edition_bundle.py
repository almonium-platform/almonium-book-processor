"""Fetch editions from a configured target and land them here.

This is promotion in the other direction, for an environment the target
cannot reach: a laptop pulls from staging with the same token it pushes with,
and staging never has to know the laptop exists.
"""

from __future__ import annotations

from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from almonium_book_processor.catalog.promotion import (
    PromotionError,
    import_bundle,
    promotion_target,
    promotion_targets,
    queue_publications,
    source_compatibility_problem,
)
from almonium_book_processor.catalog.promotion_client import PromotionClient


class Command(BaseCommand):
    help = "Pull edition bundles from a promotion target and import them here."

    def add_arguments(self, parser) -> None:
        parser.add_argument("target", help="A name from ALMONIUM_BOOKS_PROMOTION_TARGETS.")
        parser.add_argument("slugs", nargs="*", help="Editions to pull; each carries its sources.")
        parser.add_argument(
            "--all",
            action="store_true",
            help="Pull every edition the target offers; sources come with what was made from them.",
        )
        parser.add_argument(
            "--publish",
            action="store_true",
            help="Queue this environment's publication of the landed editions afterwards.",
        )
        parser.add_argument(
            "--save",
            default=None,
            metavar="DIR",
            help="Also keep each bundle as DIR/<slug>.zip.",
        )

    def handle(self, *args, **options) -> None:
        target = promotion_target(options["target"])
        if target is None:
            known = ", ".join(item.name for item in promotion_targets()) or "none"
            raise CommandError(
                f"No promotion target named {options['target']!r} is configured here "
                f"(configured: {known})."
            )
        if bool(options["slugs"]) == options["all"]:
            raise CommandError("Name the editions to pull, or pass --all for everything.")
        client = PromotionClient(target)
        try:
            listing = client.exports()
        except PromotionError as error:
            raise CommandError(str(error)) from error
        problem = source_compatibility_problem(listing)
        if problem:
            raise CommandError(problem)
        offered = {entry["slug"]: entry for entry in listing["editions"]}
        if options["all"]:
            sources = {entry["source_edition"] for entry in offered.values()}
            slugs = [slug for slug in offered if slug not in sources]
        else:
            missing = [slug for slug in options["slugs"] if slug not in offered]
            if missing:
                raise CommandError(
                    f"{target.name} does not offer {', '.join(missing)}; only reviewed "
                    "editions of public works travel."
                )
            slugs = list(dict.fromkeys(options["slugs"]))
        if not slugs:
            self.stdout.write(f"{target.name} offers nothing to pull.")
            return
        save_dir = Path(options["save"]) if options["save"] else None
        if save_dir:
            save_dir.mkdir(parents=True, exist_ok=True)
        landed: list[str] = []
        for slug in slugs:
            try:
                bundle = client.pull(slug)
                if save_dir:
                    (save_dir / f"{slug}.zip").write_bytes(bundle)
                result = import_bundle(bundle, origin=listing.get("origin"))
            except PromotionError as error:
                raise CommandError(f"{slug}: {error}") from error
            self.stdout.write(
                f"{slug}: imported {', '.join(result['imported']) or 'nothing'}; "
                f"already current: {', '.join(result['skipped']) or 'nothing'}."
            )
            landed.extend(result["imported"] + result["skipped"])
        if options["publish"]:
            queued = queue_publications(list(dict.fromkeys(landed)))
            self.stdout.write(f"Publication queued for {', '.join(queued) or 'nothing'}.")
