"""Cut an ingested source again without rewriting a word of it or of its adaptations.

A better splitter does not change a book's words, only which chapter each paragraph belongs
to. Re-ingesting would purge the adaptations and write them again; the owner will not spend
that twice. A re-cut parses the stored file with the current rules, matches every stored
paragraph to the fresh cut by its text, moves the paragraphs into the new chapters, and moves
the adaptations' paragraphs the same way, since they mirror the source block for block. The
chapters' readings are the one thing lost: there are more chapters now, and each needs its
own level and recap, which the judges give again.
"""

from __future__ import annotations

import hashlib
import re
import tempfile
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from django.db import transaction
from django.utils import timezone

from almonium_book_processor import ingest_processor_version
from almonium_book_processor.catalog.front_matter import chapter_roles
from almonium_book_processor.catalog.models import Chapter, ContentBlock, Edition, PipelineRun
from almonium_book_processor.ingest.epub import ingest_epub
from almonium_book_processor.models import BlockType, BookArtifact

# A fresh cut that fails to find this share of the stored text, or finds more new text than
# this, is not the same book cut differently: the file or the reader changed materially.
MATERIAL_CHANGE_SHARE = 0.02
LOOKAHEAD = 80


@dataclass
class RecutPlan:
    source: Edition
    old_chapters: int
    new_chapters: int
    matched: int
    stored_text_blocks: int
    fresh_text_blocks: int
    unmatched_stored: list[str] = field(default_factory=list)  # block ids
    unmatched_fresh: list[str] = field(default_factory=list)  # first words
    chapter_of_block: dict[str, int] = field(default_factory=dict)  # block id -> new chapter
    chapters: list[tuple[int, str, str]] = field(default_factory=list)  # number, title, role
    derived: list[Edition] = field(default_factory=list)
    file_sha256: str = ""

    @property
    def material_change(self) -> bool:
        stored = max(self.stored_text_blocks, 1)
        return (
            len(self.unmatched_stored) / stored > MATERIAL_CHANGE_SHARE
            or len(self.unmatched_fresh) / max(self.fresh_text_blocks, 1) > MATERIAL_CHANGE_SHARE
        )

    @property
    def unchanged(self) -> bool:
        return self.old_chapters == self.new_chapters and not self.unmatched_stored


def _plain(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def plan_recut(source: Edition) -> RecutPlan:
    """Parse the stored file with the current rules and match the stored blocks to the cut."""

    suffix = Path(source.source_file.name).suffix.lower() or ".epub"
    digest = hashlib.sha256()
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as temporary:
        with source.source_file.open("rb") as stored:
            for chunk in iter(lambda: stored.read(1024 * 1024), b""):
                digest.update(chunk)
                temporary.write(chunk)
        path = Path(temporary.name)
    try:
        artifact = ingest_epub(
            path,
            edition_slug=source.slug,
            work_slug=source.work.slug,
            title=source.title or None,
            author=source.author or None,
            language=source.language or None,
            cefr_level=source.cefr_level,
        )
    finally:
        path.unlink(missing_ok=True)
    return _match(source, artifact, digest.hexdigest())


def _match(source: Edition, artifact: BookArtifact, file_sha256: str) -> RecutPlan:
    textless = {BlockType.IMAGE.value, BlockType.SEPARATOR.value}
    stored = list(source.blocks.select_related("chapter").order_by("chapter__sequence", "sequence"))
    fresh = [(block.chapter, _plain(block.text), block.type.value) for block in artifact.blocks]
    fresh_text = [(index, chapter) for index, (chapter, text, kind) in enumerate(fresh) if text]
    plan = RecutPlan(
        source=source,
        old_chapters=source.chapters.count(),
        new_chapters=len({chapter for chapter, _, _ in fresh}),
        matched=0,
        stored_text_blocks=sum(1 for b in stored if _plain(b.text)),
        fresh_text_blocks=len(fresh_text),
        file_sha256=file_sha256,
    )
    cursor = 0
    taken: set[int] = set()
    current_chapter = fresh[0][0] if fresh else 0
    for block in stored:
        text = _plain(block.text)
        if not text or block.block_type in textless:
            plan.chapter_of_block[block.block_id] = current_chapter
            continue
        found = next(
            (
                position
                for position in range(cursor, min(cursor + LOOKAHEAD, len(fresh_text)))
                if fresh[fresh_text[position][0]][1] == text
            ),
            None,
        )
        if found is None:
            plan.unmatched_stored.append(block.block_id)
            plan.chapter_of_block[block.block_id] = current_chapter
            continue
        taken.update(range(cursor, found))  # fresh blocks passed over are new text
        index, chapter = fresh_text[found]
        plan.matched += 1
        current_chapter = chapter
        plan.chapter_of_block[block.block_id] = chapter
        cursor = found + 1
    plan.unmatched_fresh = [fresh[fresh_text[p][0]][1][:60] for p in sorted(taken)] + [
        fresh[index][1][:60] for index, _ in fresh_text[cursor:]
    ]
    titles: dict[int, str] = {}
    cut_by_size: set[int] = set()
    numbers = sorted({chapter for chapter, _, _ in fresh})
    for block in artifact.blocks:
        if (
            block.type == BlockType.HEADING
            and block.chapter not in titles
            and not block.attributes.get("part")
        ):
            titles[block.chapter] = block.text[:500]
        if block.attributes.get("cut") == "size":
            cut_by_size.add(numbers.index(block.chapter))
    roles = chapter_roles(
        [titles.get(number, "") for number in numbers],
        book_title=source.title,
        author=source.author,
        cut_by_size=cut_by_size,
    )
    plan.chapters = [
        (number, titles.get(number, ""), role) for number, role in zip(numbers, roles, strict=True)
    ]
    plan.derived = list(Edition.objects.filter(source_edition=source).order_by("created_at"))
    return plan


@transaction.atomic
def apply_recut(plan: RecutPlan) -> PipelineRun:
    """Move the stored blocks, and the derived editions' blocks, into the new chapters."""

    for edition in [plan.source, *plan.derived]:
        old = list(edition.chapters.order_by("sequence"))
        for offset, chapter in enumerate(old):
            chapter.sequence = 1_000_000 + offset  # out of the way of the new numbering
            chapter.save(update_fields=["sequence"])
        new = {
            number: Chapter.objects.create(
                edition=edition, sequence=number, title=title, analysis_role=role
            )
            for number, title, role in plan.chapters
        }
        counters: dict[int, int] = defaultdict(int)
        last = plan.chapters[0][0]
        for block in edition.blocks.select_related("chapter").order_by(
            "chapter__sequence", "sequence"
        ):
            number = plan.chapter_of_block.get(block.block_id, last)
            last = number
            counters[number] += 1
            # a fresh row keeps the unique (chapter, sequence) pair from colliding mid-move
            ContentBlock.objects.filter(pk=block.pk).update(
                chapter=new[number], sequence=1_000_000 + counters[number]
            )
        for number in new:
            for position, block in enumerate(
                ContentBlock.objects.filter(chapter=new[number]).order_by("sequence"), 1
            ):
                ContentBlock.objects.filter(pk=block.pk).update(sequence=position)
        Chapter.objects.filter(pk__in=[chapter.pk for chapter in old]).delete()
    return PipelineRun.objects.create(
        edition=plan.source,
        stage=PipelineRun.Stage.INGEST,
        processor_version=ingest_processor_version(),
        status=PipelineRun.Status.SUCCEEDED,
        input_hash=plan.file_sha256,
        idempotency_key=f"{plan.source.id}:{plan.file_sha256}:recut:{uuid.uuid4().hex}",
        progress=100,
        finished_at=timezone.now(),
        summary={
            "recut": True,
            "old_chapters": plan.old_chapters,
            "new_chapters": plan.new_chapters,
            "matched_blocks": plan.matched,
            "unmatched_stored": plan.unmatched_stored[:50],
            "unmatched_fresh": plan.unmatched_fresh[:50],
            "derived": [edition.slug for edition in plan.derived],
        },
    )
