"""Archive verified digital wrappers and merge chapters that began at print-page markers."""

from collections import Counter, defaultdict
from pathlib import PurePosixPath
from zipfile import BadZipFile, ZipFile

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from almonium_book_processor import __version__, ingest_processor_version
from almonium_book_processor.catalog.image_cleanup import (
    _analysis_plan,
    _carry,
    _carry_analysis,
    _sentence_hash,
)
from almonium_book_processor.catalog.models import (
    BlockAlignment,
    Chapter,
    ChapterAlignment,
    ContentBlock,
    Edition,
    EditionArtifact,
    GlossNote,
    PipelineRun,
    TextQualityFinding,
)
from almonium_book_processor.catalog.offline_sentence_alignment import queue_alignment
from almonium_book_processor.catalog.page_cleanup import _current_alignments
from almonium_book_processor.ingest.common import HEADING_TAGS, normalize_text, parse_html
from almonium_book_processor.ingest.digital_wrappers import is_digital_wrapper
from almonium_book_processor.ingest.page_markers import MARKUP_HINT, page_markers

_CLEANUP = {"cleanup": "wrapper_cleanup", "reason": "verified_digital_wrapper_removed"}


def _evidence(source):
    page_labels = set()
    wrappers = set()
    with source.source_file.open("rb") as stream, ZipFile(stream) as archive:
        for path in archive.namelist():
            if not path.lower().endswith((".html", ".xhtml", ".htm")):
                continue
            data = archive.read(path)
            lower = data.lower()
            doc = PurePosixPath(path).name
            if not (
                MARKUP_HINT.search(data)
                or any(
                    hint in lower
                    for hint in (b"gutenberg", b"ebook", b"runeberg", b"gallica", b"encoding:")
                )
            ):
                continue
            root = parse_html(data)
            containers = {}
            for tag in page_markers(root):
                label = normalize_text(tag)
                if not label.isdecimal():
                    continue
                for parent in (tag, *tag.parents):
                    if parent.name in (HEADING_TAGS | {"p"}) and normalize_text(parent) == label:
                        containers[id(parent)] = label
            ambiguous = set()
            for tag in root.find_all(["p", *HEADING_TAGS]):
                text = normalize_text(tag)
                if is_digital_wrapper(text):
                    wrappers.add((doc, text))
                if text.isdecimal() and id(tag) not in containers:
                    ambiguous.add(text)
            page_labels.update((doc, label) for label in set(containers.values()) - ambiguous)
    return page_labels, wrappers


def plan_source_wrappers(work=None):
    originals = Edition.objects.filter(
        edition_type=Edition.EditionType.ORIGINAL,
        work__visibility="public",
        withdrawal_requested_at=None,
        source_file__iendswith=".epub",
    ).order_by("slug")
    if work:
        originals = originals.filter(work__slug=work)
    editions = defaultdict(dict)
    counts = Counter()
    for source in originals.iterator():
        counts["source EPUBs scanned"] += 1
        try:
            pages, wrappers = _evidence(source)
        except (BadZipFile, FileNotFoundError):
            counts["source EPUBs unavailable"] += 1
            continue
        if not pages and not wrappers:
            continue
        groups = {}
        for block in source.blocks.select_related("chapter"):
            ref = PurePosixPath(block.source_ref.split("#", 1)[0]).name
            key = (ref, block.text)
            if key in wrappers:
                kind = "digital wrapper"
            elif (
                key in pages
                and block.block_type == ContentBlock.BlockType.HEADING
                and block.chapter.title == block.text
                and block.sequence == 1
            ):
                kind = "false page heading"
            else:
                continue
            editions[source.pk][block.pk] = (kind, block.text)
            if block.align_group:
                groups[block.align_group] = (kind, block.text)
        companions = (
            ContentBlock.objects.filter(
                edition__work=source.work,
                edition__withdrawal_requested_at=None,
                align_group__in=groups,
            )
            .exclude(edition=source)
            .select_related("chapter")
        )
        for block in companions:
            kind, text = groups[block.align_group]
            if kind == "false page heading" and not (
                block.block_type == ContentBlock.BlockType.HEADING
                and block.sequence == 1
                and block.text == block.chapter.title == text
            ):
                continue
            editions[block.edition_id][block.pk] = (kind, block.text)
    for targets in editions.values():
        counts.update(kind for kind, _ in targets.values())
    return editions, counts


def _merge_chapters(edition, false_headings):
    chapters = list(edition.chapters.order_by("sequence"))
    if not false_headings:
        return []
    if ChapterAlignment.objects.filter(
        Q(source_chapter_id__in=false_headings) | Q(target_chapter_id__in=false_headings)
    ).exists():
        raise ValueError(f"{edition.slug} has explicit chapter alignments.")
    archived = []
    first_real = next((chapter for chapter in chapters if chapter.pk not in false_headings), None)
    parent = None
    kept = []
    for chapter in chapters:
        if chapter.pk not in false_headings:
            kept.append(chapter)
            parent = chapter
            continue
        blocks = list(chapter.blocks.order_by("sequence"))
        if parent is None:
            if blocks or first_real is None:
                raise ValueError(f"{edition.slug} begins with an unmatched page heading.")
            parent = first_real
        archived.append(
            {
                "id": str(chapter.pk),
                "title": chapter.title,
                "sequence": chapter.sequence,
                "analysis_role": chapter.analysis_role,
                "block_ids": [block.block_id for block in blocks],
                "merged_into": str(parent.pk),
            }
        )
        high = parent.blocks.order_by("-sequence").values_list("sequence", flat=True).first() or 0
        for index, block in enumerate(blocks, start=high + 1):
            block.chapter_id = parent.pk
            block.sequence = index
        ContentBlock.objects.bulk_update(blocks, ["chapter", "sequence"])
        GlossNote.objects.filter(chapter=chapter).update(chapter=parent)
        history = EditionArtifact.objects.filter(chapter=chapter)
        history.filter(kind=EditionArtifact.Kind.SENTENCE_ALIGNMENT).update(chapter=parent)
        history.exclude(kind=EditionArtifact.Kind.SENTENCE_ALIGNMENT).update(
            chapter=parent, is_current=False
        )
        chapter.delete()
    # The surviving sequence numbers only decrease, so updating in order vacates each slot.
    first = chapters[0].sequence
    for sequence, chapter in enumerate(kept, first):
        if chapter.sequence != sequence:
            Chapter.objects.filter(pk=chapter.pk).update(sequence=sequence)
    return archived


@transaction.atomic
def apply_source_wrappers(targets):
    from almonium_book_processor.catalog.tasks import analyze_edition_lexicon

    counts = Counter()
    block_ids = {pk for items in targets.values() for pk in items}
    blocks = ContentBlock.objects.select_for_update().filter(pk__in=block_ids).order_by("id")
    by_edition = defaultdict(list)
    for block in blocks:
        if targets[block.edition_id][block.pk][1] != block.text:
            raise ValueError("Source text changed since the scan.")
        by_edition[block.edition_id].append(block)
    if sum(map(len, by_edition.values())) != len(block_ids):
        raise ValueError("Source blocks changed since the scan.")
    editions = list(Edition.objects.select_for_update().filter(pk__in=targets).order_by("id"))
    if PipelineRun.objects.filter(
        edition__work_id__in={edition.work_id for edition in editions},
        status__in=(PipelineRun.Status.QUEUED, PipelineRun.Status.RUNNING),
    ).exists():
        raise ValueError("An affected work has a queued or running job.")
    if (
        GlossNote.objects.filter(block_id__in=block_ids).exists()
        or BlockAlignment.objects.filter(
            Q(source_block_id__in=block_ids) | Q(target_block_id__in=block_ids)
        ).exists()
    ):
        raise ValueError("A wrapper block has an explicit gloss or alignment.")
    alignments = _current_alignments(block_ids, targets)
    for edition in editions:
        rows = by_edition[edition.pk]
        kinds = targets[edition.pk]
        chapter_ids = {row.chapter_id for row in rows if kinds[row.pk][0] == "false page heading"}
        successful = edition.pipeline_runs.filter(status=PipelineRun.Status.SUCCEEDED)
        sentences = successful.filter(
            stage=PipelineRun.Stage.SENTENCES, input_hash=_sentence_hash(edition)
        ).first()
        analysis = successful.filter(stage=PipelineRun.Stage.CHAPTER_ANALYSIS).first()
        before = _analysis_plan(edition, analysis) if analysis and not chapter_ids else None
        removed = [
            {
                "id": str(row.pk),
                "block_id": row.block_id,
                "kind": kinds[row.pk][0],
                "chapter_id": str(row.chapter_id),
                "sequence": row.sequence,
                "block_type": row.block_type,
                "text": row.text,
                "sentences": row.sentences,
                "source_ref": row.source_ref,
                "attributes": row.attributes,
                "align_group": str(row.align_group) if row.align_group else None,
            }
            for row in rows
        ]
        ids = [row.pk for row in rows]
        TextQualityFinding.objects.filter(
            block_id__in=ids, status=TextQualityFinding.Status.OPEN
        ).update(status=TextQualityFinding.Status.SUPERSEDED)
        ContentBlock.objects.filter(pk__in=ids).delete()
        counts["false chapters merged"] += len(chapter_ids)
        changed_titles = []
        for row in rows:
            if row.block_type != ContentBlock.BlockType.HEADING or row.chapter_id in chapter_ids:
                continue
            chapter = row.chapter
            if chapter.title != row.text:
                continue
            new_title = (
                chapter.blocks.filter(block_type=ContentBlock.BlockType.HEADING)
                .order_by("sequence")
                .values_list("text", flat=True)
                .first()
            )
            if new_title is None and not chapter.blocks.exists():
                chapter_ids.add(chapter.pk)
            else:
                changed_titles.append({"id": str(chapter.pk), "old_title": chapter.title})
                Chapter.objects.filter(pk=chapter.pk).update(title=(new_title or "")[:500])
        archived_chapters = _merge_chapters(edition, chapter_ids)
        digest = _sentence_hash(edition)
        PipelineRun.objects.create(
            edition=edition,
            stage=PipelineRun.Stage.INGEST,
            processor_version=ingest_processor_version(),
            status=PipelineRun.Status.SUCCEEDED,
            progress=100,
            finished_at=timezone.now(),
            input_hash=digest,
            idempotency_key=f"{edition.pk}:source-wrappers:{digest}",
            summary={
                "source_wrapper_archive": {
                    "blocks": removed,
                    "chapters": archived_chapters,
                    "titles": changed_titles,
                }
            },
        )
        current = list(edition.blocks.values_list("text", "sentences"))
        Edition.objects.filter(pk=edition.pk).update(
            word_count=sum(len(text.split()) for text, _ in current)
        )
        if sentences:
            _carry(
                sentences,
                f"{edition.pk}:{digest}:sentences:{__version__}",
                digest,
                {
                    **sentences.summary,
                    "blocks": sum(bool(text) for text, _ in current),
                    "sentences": sum(len(spans) for _, spans in current),
                },
                **_CLEANUP,
            )
            counts["sentence runs carried"] += 1
        if before and analysis and not archived_chapters:
            counts[_carry_analysis(edition, analysis, before, **_CLEANUP)] += 1
        elif analysis:
            counts["chapter layouts changed with saved readings"] += 1
        if edition.artifacts.filter(
            kind=EditionArtifact.Kind.USEFUL_WORDS, is_current=True
        ).exists():
            transaction.on_commit(lambda pk=str(edition.pk): analyze_edition_lexicon.delay(pk))
            counts["local vocabulary jobs"] += 1
    for previous, hashes in alignments:
        queue_alignment(
            previous.edition_id,
            previous.summary["secondary_id"],
            model=previous.summary["model"],
            local_only=True,
        )
        EditionArtifact.objects.filter(
            edition_id=previous.edition_id,
            kind=EditionArtifact.Kind.SENTENCE_ALIGNMENT,
            input_hash__in=hashes,
        ).update(is_current=False)
        counts["local alignment jobs"] += 1
    return counts
