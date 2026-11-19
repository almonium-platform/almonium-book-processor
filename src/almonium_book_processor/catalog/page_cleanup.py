"""Plan an in-place bibliography cleanup using the retained EPUB as evidence."""

import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import PurePosixPath
from zipfile import BadZipFile, ZipFile

from django.db import transaction
from django.utils import timezone

from almonium_book_processor import __version__
from almonium_book_processor.catalog.image_cleanup import (
    _alignment_runs,
    _analysis_plan,
    _carry,
    _carry_analysis,
    _sentence_hash,
)
from almonium_book_processor.catalog.models import (
    ContentBlock,
    Edition,
    EditionArtifact,
    PipelineRun,
)
from almonium_book_processor.catalog.offline_sentence_alignment import (
    _digest,
    processor_version,
    queue_alignment,
)
from almonium_book_processor.catalog.parallel_content import inherited_pairs, pair_hash
from almonium_book_processor.ingest.common import normalize_text, parse_html
from almonium_book_processor.ingest.page_markers import MARKUP_HINT, page_markers
from almonium_book_processor.processing.nlp import split_sentences
from almonium_book_processor.processing.punctuation import fold_punctuation

_CLEANUP = {"cleanup": "page_cleanup", "reason": "source_tagged_print_page_removed"}

_TEXT_CONTAINERS = {"p", "div", "li", "pre", "blockquote", "aside", "figcaption", "td"}
_BRACKETED = re.compile(r"\[\s*(?:(?:pg\.?|page|p\.|seite)\s+)?\d{1,5}\s*\]", re.I)


@dataclass(frozen=True)
class PageEdit:
    block: ContentBlock
    text: str
    source_block_id: str


def _marker_key(label):
    return re.sub(r"\s+", "", label).casefold()


def _source_paragraphs(source):
    """Find exact before/after text and the labels that the markup proves."""
    results = defaultdict(set)
    with source.source_file.open("rb") as stream, ZipFile(stream) as archive:
        for path in archive.namelist():
            if not path.lower().endswith((".xhtml", ".html", ".htm")):
                continue
            data = archive.read(path)
            if not MARKUP_HINT.search(data):
                continue
            root = parse_html(data)
            marks = [tag for tag in page_markers(root) if tag.get_text().strip()]
            ancestors = {}
            for tag in marks:
                label = normalize_text(tag)
                for parent in tag.parents:
                    if parent.name in {"html", "body"}:
                        break
                    if parent.name in _TEXT_CONTAINERS:
                        _, _, labels = ancestors.setdefault(
                            id(parent), (parent, normalize_text(parent), [])
                        )
                        labels.append(label)
            for tag in reversed(marks):
                tag.decompose()
            for parent, before, labels in ancestors.values():
                after = normalize_text(parent)
                if before and after and before != after:
                    results[PurePosixPath(path).name, before].add((after, tuple(labels)))
    return results


def _companion_text(text, source_text, labels):
    expected = Counter(_marker_key(label) for label in labels if _BRACKETED.fullmatch(label))
    if not expected:
        return text
    source_counts = Counter(_marker_key(m[0]) for m in _BRACKETED.finditer(source_text))
    target_counts = Counter(_marker_key(m[0]) for m in _BRACKETED.finditer(text))
    # The same number can name a footnote in a paragraph. Remove a label only
    # when every occurrence in the source was tagged and the companion kept all of them.
    keys = {
        key for key, count in expected.items() if source_counts[key] == target_counts[key] == count
    }
    cleaned = _BRACKETED.sub(lambda m: "" if _marker_key(m[0]) in keys else m[0], text)
    return re.sub(r"\s{2,}", " ", cleaned).strip() if cleaned != text else text


def plan_page_cleanup(work=None):
    sources = Edition.objects.filter(
        edition_type=Edition.EditionType.ORIGINAL,
        work__visibility="public",
        withdrawal_requested_at=None,
        source_file__iendswith=".epub",
    ).order_by("slug")
    if work:
        sources = sources.filter(work__slug=work)
    edits = {}
    stats = Counter()
    for source in sources.iterator():
        stats["source EPUBs scanned"] += 1
        try:
            paragraph_text = _source_paragraphs(source)
        except (FileNotFoundError, BadZipFile):
            stats["source EPUBs unavailable"] += 1
            continue
        if not paragraph_text:
            continue
        proof = {}
        for block in source.blocks.exclude(text="").exclude(
            block_type=ContentBlock.BlockType.IMAGE
        ):
            key = PurePosixPath(block.source_ref.split("#", 1)[0]).name, block.text
            matches = paragraph_text.get(key, ())
            if len(matches) != 1:
                continue
            after, labels = next(iter(matches))
            edits[block.pk] = PageEdit(block, after, block.block_id)
            if block.align_group:
                proof[block.align_group] = (block, after, labels)
        if not proof:
            continue
        companions = (
            ContentBlock.objects.filter(
                edition__work_id=source.work_id,
                edition__withdrawal_requested_at=None,
                align_group__in=proof,
            )
            .exclude(edition_id=source.pk)
            .exclude(text="")
            .exclude(block_type=ContentBlock.BlockType.IMAGE)
        )
        for block in companions:
            original, cleaned, labels = proof[block.align_group]
            after = (
                cleaned
                if block.text == original.text
                else _companion_text(block.text, original.text, labels)
            )
            if after and after != block.text:
                edits[block.pk] = PageEdit(block, after, original.block_id)
    return list(edits.values()), stats


def _spans(block, language):
    spans = []
    cursor = 0
    for sentence in split_sentences(block.text, language):
        start = block.text.index(sentence, cursor)
        cursor = start + len(sentence)
        spans.append({"start": start, "end": cursor})
    return [
        {"id": f"{block.block_id}.s{index}", **span}
        for index, span in enumerate(fold_punctuation(block.text, spans, language), 1)
    ]


def _current_alignments(changes, edition_ids):
    current = {}
    for run in _alignment_runs(edition_ids):
        primary, secondary = (
            Edition.objects.get(pk=pk) for pk in (run.edition_id, run.summary["secondary_id"])
        )
        key = frozenset((primary.pk, secondary.pk))
        if key in current or processor_version(run.summary["model"]) != run.processor_version:
            continue
        pairs = inherited_pairs(primary, secondary)
        if pairs and _digest(pairs) == run.input_hash:
            touched = [
                pair_hash(left, right)
                for left, right in pairs
                if left.pk in changes or right.pk in changes
            ]
            if touched:
                current[key] = (run, touched)
    return current.values()


@transaction.atomic
def apply_page_cleanup(edits):
    from almonium_book_processor.catalog.tasks import analyze_edition_lexicon

    stats = Counter()
    changes = {edit.block.pk: edit for edit in edits}
    locked = ContentBlock.objects.select_for_update().filter(pk__in=changes).order_by("id")
    by_edition = defaultdict(list)
    for block in locked:
        edit = changes[block.pk]
        if block.text != edit.block.text or "legacy_page_text" in block.attributes:
            raise ValueError(f"Content changed after preview: {block.block_id}")
        by_edition[block.edition_id].append(block)
    if sum(map(len, by_edition.values())) != len(changes):
        raise ValueError("A block disappeared after preview.")
    editions = list(Edition.objects.select_for_update().filter(pk__in=by_edition).order_by("id"))
    if PipelineRun.objects.filter(
        edition__work_id__in={edition.work_id for edition in editions},
        status__in=(PipelineRun.Status.QUEUED, PipelineRun.Status.RUNNING),
    ).exists():
        raise ValueError("An affected work has a queued or running job.")
    alignments = _current_alignments(changes, by_edition)
    for edition in editions:
        successful = edition.pipeline_runs.filter(status=PipelineRun.Status.SUCCEEDED)
        sentence = successful.filter(
            stage=PipelineRun.Stage.SENTENCES, input_hash=_sentence_hash(edition)
        ).first()
        analysis = successful.filter(stage=PipelineRun.Stage.CHAPTER_ANALYSIS).first()
        before = _analysis_plan(edition, analysis) if analysis else None
        for block in by_edition[edition.pk]:
            edit = changes[block.pk]
            block.attributes = {
                **block.attributes,
                "legacy_page_text": {
                    "text": block.text,
                    "sentences": block.sentences,
                    "source_block_id": edit.source_block_id,
                },
            }
            block.text = edit.text
            block.sentences = _spans(block, edition.language)
            block.updated_at = timezone.now()
        ContentBlock.objects.bulk_update(
            by_edition[edition.pk], ["text", "sentences", "attributes", "updated_at"]
        )
        text_and_spans = list(edition.blocks.values_list("text", "sentences"))
        Edition.objects.filter(pk=edition.pk).update(
            word_count=sum(len(text.split()) for text, _ in text_and_spans)
        )
        if sentence:
            digest = _sentence_hash(edition)
            _carry(
                sentence,
                f"{edition.pk}:{digest}:sentences:{__version__}",
                digest,
                {**sentence.summary, "sentences": sum(len(spans) for _, spans in text_and_spans)},
                **_CLEANUP,
            )
            stats["sentence runs carried"] += 1
        if analysis:
            stats[_carry_analysis(edition, analysis, before, **_CLEANUP)] += 1
        if edition.artifacts.filter(
            kind=EditionArtifact.Kind.USEFUL_WORDS, is_current=True
        ).exists():
            transaction.on_commit(lambda pk=str(edition.pk): analyze_edition_lexicon.delay(pk))
            stats["local vocabulary jobs"] += 1

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
            is_current=True,
        ).update(is_current=False)
        stats["local alignment jobs"] += 1
        stats["changed aligned paragraph pairs"] += len(hashes)
    stats["blocks cleaned"] = len(changes)
    return stats
