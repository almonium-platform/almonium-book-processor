"""Queue the offline sentence alignment of every public original with each edition made from it.

The pipeline queues new books by itself; this catches up the books that existed before
it did. Pairs already current or under way are skipped, so running it twice queues
nothing new. Originals are queued one after another with all their companions, so the
aligner embeds an original once and reuses it for the rest.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand

from almonium_book_processor.catalog.models import Edition, Work
from almonium_book_processor.catalog.sentence_alignment_queue import made_from, queue_pair


class Command(BaseCommand):
    help = "Queue offline sentence alignment for every public original and its companions."

    def add_arguments(self, parser) -> None:
        parser.add_argument("--work", help="Only this work's slug.")
        parser.add_argument(
            "--dry-run", action="store_true", help="List what would be queued; queue nothing."
        )

    def handle(self, *args, work=None, dry_run=False, **options) -> None:
        from almonium_book_processor.catalog.parallel_status import pair_status

        originals = Edition.objects.filter(
            work__visibility=Work.Visibility.PUBLIC,
            source_edition__isnull=True,
            withdrawal_requested_at=None,
        ).order_by("work__slug", "slug")
        if work:
            originals = originals.filter(work__slug=work)
        queued = skipped = 0
        for original in originals:
            for other in made_from(original):
                if dry_run:
                    state = pair_status(original, other)["state"]
                    waiting = state not in {"current", "running", "incomplete"}
                    self.stdout.write(f"{'queue' if waiting else state:>10}  {other.slug}")
                    queued += waiting
                    skipped += not waiting
                    continue
                if queue_pair(original, other):
                    queued += 1
                else:
                    skipped += 1
        verb = "would queue" if dry_run else "queued"
        self.stdout.write(f"{verb} {queued} pair(s); {skipped} current, under way or incomplete.")
