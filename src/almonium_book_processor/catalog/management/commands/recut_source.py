from django.core.management.base import BaseCommand, CommandError

from almonium_book_processor.catalog.models import Edition
from almonium_book_processor.catalog.recut import apply_recut, plan_recut


class Command(BaseCommand):
    help = (
        "Cut an ingested source again with the current rules, moving its paragraphs and its "
        "adaptations' paragraphs into the new chapters without rewriting a word. Reports what "
        "would change; --apply does it. Refuses a file whose text changed materially."
    )

    def add_arguments(self, parser):
        parser.add_argument("slugs", nargs="+")
        parser.add_argument("--apply", action="store_true")

    def handle(self, *args, **options):
        for slug in options["slugs"]:
            source = Edition.objects.filter(slug=slug).select_related("work").first()
            if source is None:
                raise CommandError(f"No edition {slug}.")
            plan = plan_recut(source)
            self.stdout.write(
                f"{slug}: {plan.old_chapters} -> {plan.new_chapters} chapters; "
                f"{plan.matched}/{plan.stored_text_blocks} stored paragraphs found in the fresh "
                f"cut, {len(plan.unmatched_fresh)} fresh paragraphs new; derived: "
                + (", ".join(e.slug for e in plan.derived) or "none")
            )
            if plan.material_change:
                self.stdout.write(self.style.WARNING("  the text changed materially; not re-cut"))
                for block_id in plan.unmatched_stored[:5]:
                    self.stdout.write(f"    stored but not found: {block_id}")
                for text in plan.unmatched_fresh[:5]:
                    self.stdout.write(f"    fresh but not stored: {text}")
                continue
            if plan.unchanged:
                self.stdout.write("  same cut already")
                continue
            if options["apply"]:
                run = apply_recut(plan)
                self.stdout.write(self.style.SUCCESS(f"  re-cut; ingest run {run.id}"))
