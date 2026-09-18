"""Group pilots judged and audited by hand-run scripts into a floor probe record."""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from almonium_book_processor.catalog.adaptation_floor import backfill_probe
from almonium_book_processor.catalog.models import Edition


class Command(BaseCommand):
    help = (
        "Record a floor probe at a level from existing standalone pilots on a source edition, "
        "provided they were generated, judged and audited exactly as a probe would today."
    )

    def add_arguments(self, parser) -> None:
        parser.add_argument("edition_slug", help="The source edition the pilots hang off.")
        parser.add_argument("target_level", choices=["B2", "B1"])

    def handle(self, *args, **options) -> None:
        edition = Edition.objects.filter(slug=options["edition_slug"]).first()
        if edition is None:
            raise CommandError("No edition has that slug.")
        try:
            run = backfill_probe(edition, options["target_level"])
        except ValueError as error:
            raise CommandError(str(error)) from error
        summary = run.summary
        self.stdout.write(
            f"Probe {run.id} {summary['verdict']} from {len(summary['results'])} pilot(s): "
            + ("; ".join(summary["reasons"]) or "judge at target, audits clean")
            + f". adapts_to is now {edition.work.adapts_to or 'unset'}."
        )
        for result in summary["results"]:
            self.stdout.write(
                f"  {result['title']}: judge {result['judge_max_level']}, "
                f"{result['material']} material / {result['minor']} minor / "
                f"{result['uncertain']} uncertain, pilot {result['pilot_id']}"
            )
