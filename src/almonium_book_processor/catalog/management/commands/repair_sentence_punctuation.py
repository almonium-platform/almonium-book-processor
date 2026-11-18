"""Join the punctuation-only "sentences" spaCy made to the sentences they belong to.

Sentence splitting folds a lone «, » or dialogue dash as it splits
(processing/punctuation.py). This repairs the editions split before it did, in place and
without running spaCy again: only blocks that hold such a piece change, every other
boundary and every other block stays as it was, and the alignment of the pairs a changed
edition is in is queued again (it embeds only the paragraphs whose spans moved).
"""

from __future__ import annotations

from collections import Counter

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from almonium_book_processor.catalog.models import ContentBlock, Edition
from almonium_book_processor.processing.punctuation import fold_punctuation


def repaired(block: ContentBlock, language: str) -> list[dict] | None:
    """The block's folded sentences, numbered, or None when folding changes nothing."""

    spans = [{"start": s["start"], "end": s["end"]} for s in block.sentences or []]
    folded = fold_punctuation(block.text, spans, language)
    if folded == spans:
        return None
    return [{"id": f"{block.block_id}.s{number}", **span} for number, span in enumerate(folded, 1)]


class Command(BaseCommand):
    help = "Fold punctuation-only sentences into their neighbours and re-queue alignment."

    def add_arguments(self, parser) -> None:
        parser.add_argument("--language", help="Only editions in this language.")
        parser.add_argument("--edition", help="Only this edition's slug.")
        parser.add_argument(
            "--dry-run", action="store_true", help="Count what would change; change nothing."
        )

    def handle(self, *args, language=None, edition=None, dry_run=False, **options) -> None:
        from almonium_book_processor.catalog.sentence_alignment_queue import queue_for

        editions = Edition.objects.order_by("language", "slug")
        if language:
            editions = editions.filter(language=language)
        if edition:
            editions = editions.filter(slug=edition)
        blocks_by_language, sentences_by_language = Counter(), Counter()
        changed = []
        for item in editions:
            with transaction.atomic():
                blocks = (
                    item.blocks.exclude(text="")
                    .only("id", "block_id", "text", "sentences", "updated_at")
                    .order_by("id")
                )
                if not dry_run:
                    blocks = blocks.select_for_update()
                updates = []
                for block in blocks:
                    sentences = repaired(block, item.language)
                    if sentences is None:
                        continue
                    sentences_by_language[item.language] += len(block.sentences) - len(sentences)
                    blocks_by_language[item.language] += 1
                    block.sentences = sentences
                    block.updated_at = timezone.now()
                    updates.append(block)
                if updates and not dry_run:
                    ContentBlock.objects.bulk_update(
                        updates, ["sentences", "updated_at"], batch_size=1000
                    )
            if updates:
                changed.append(item)
        queued = 0
        if not dry_run:
            for item in changed:
                queued += len(queue_for(item))
        verb = "would fold" if dry_run else "folded"
        for code in sorted(blocks_by_language, key=lambda c: -sentences_by_language[c]):
            self.stdout.write(
                f"{code}: {verb} {sentences_by_language[code]} punctuation-only sentence(s) "
                f"in {blocks_by_language[code]} block(s)"
            )
        self.stdout.write(
            f"{len(changed)} edition(s) {'would change' if dry_run else 'changed'}; "
            f"{queued} alignment run(s) queued."
        )
