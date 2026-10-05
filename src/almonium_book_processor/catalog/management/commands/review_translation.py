from django.core.management.base import BaseCommand, CommandError

from almonium_book_processor.ai.codex_provider import codex_meter
from almonium_book_processor.catalog.models import Edition
from almonium_book_processor.catalog.translation_review import review_translation


class Command(BaseCommand):
    help = (
        "Have two editors read a machine translation beside its source and queue what they find "
        "in the edition's fidelity findings. The editors run through the Claude Code and Codex "
        "CLIs, so run this on the machine where they are signed in."
    )

    def add_arguments(self, parser):
        parser.add_argument("edition_slug")
        parser.add_argument("--chapters", nargs="+", type=int, help="chapter sequences to review")
        parser.add_argument("--workers", type=int, default=4, help="windows read at a time")

    def handle(self, *args, **options):
        try:
            edition = Edition.objects.get(slug=options["edition_slug"])
        except Edition.DoesNotExist as error:
            raise CommandError(f"No edition with slug {options['edition_slug']}") from error
        before = codex_meter()
        run = review_translation(
            str(edition.id), chapters=options["chapters"], workers=options["workers"]
        )
        after = codex_meter()
        if before and after:
            # kept with the run: meter points beside the run's tokens are what the plan's
            # share of the list price is measured from
            run.summary = {**run.summary, "codex_meter": {"before": before, "after": after}}
            run.save(update_fields=["summary", "updated_at"])
            self.stdout.write(
                f"Codex meter: {before['used_percent']:.0f}% to {after['used_percent']:.0f}% "
                "of the week"
            )
        review = run.summary.get("review") or {}
        agreement = review.get("agreement") or {}
        self.stdout.write(
            f"{run.status}: {len(review.get('issues', []))} findings "
            f"(raised by both {agreement.get('both', 0)}, "
            f"confirmed by the other {agreement.get('confirmed', 0)}, "
            f"disputed {agreement.get('disputed', 0)})"
        )
