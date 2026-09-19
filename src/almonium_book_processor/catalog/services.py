from __future__ import annotations

import hashlib
import json
import logging
import uuid
from collections.abc import Iterable
from pathlib import Path
from typing import BinaryIO

from django.contrib.auth.models import AbstractBaseUser
from django.core.files import File
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from almonium_book_processor.artifact_migrations import migrate_artifact_payload
from almonium_book_processor.catalog.models import (
    AlignmentGroupReview,
    BlockAlignment,
    Chapter,
    ChapterAlignment,
    ContentBlock,
    ContentBlockRevision,
    Edition,
    PipelineRun,
    QAWarning,
    ReviewDecision,
    TextQualityFinding,
    Work,
)
from almonium_book_processor.models import (
    BookArtifact,
    IngestionWarningSeverity,
    ingestion_warning_severity,
)
from almonium_book_processor.titles import calm_title

BULK_DETACHED_INITIAL_MIN_CONFIDENCE = 0.9

logger = logging.getLogger(__name__)


def hash_uploaded_file(upload: BinaryIO) -> str:
    digest = hashlib.sha256()
    for chunk in iter(lambda: upload.read(1024 * 1024), b""):
        digest.update(chunk)
    upload.seek(0)
    return digest.hexdigest()


@transaction.atomic
def create_source_edition(
    *,
    source_file: File,
    edition_type: str = Edition.EditionType.ORIGINAL,
    work: Work | None = None,
    cefr_level: str | None = None,
    work_slug: str = "",
    work_title: str = "",
    author: str = "",
    description: str = "",
    original_language: str = "",
    publication_year: int | None = None,
    cover_url: str = "",
    edition_slug: str = "",
    edition_title: str = "",
    language: str = "",
) -> Edition:
    """Queue a catalogue source; every bibliographic field is an optional pin.

    Blank fields are read from the file header and completed by the metadata
    stage, which also replaces provisional slugs with ones derived from the
    detected title. Pinned values are recorded as the editor's and never
    overridden.

    An upload is always an independently imported text: it joins ``work`` (or
    the work ``work_slug`` names) and never claims a source edition, which is
    reserved for editions generated block for block.
    """

    from almonium_book_processor.catalog.metadata import (
        PROVENANCE_USER,
        initial_provenance,
        provisional_slug,
    )

    work_title, author, edition_title = (
        calm_title(work_title),
        calm_title(author),
        calm_title(edition_title),
    )
    pinned = initial_provenance(
        title=work_title,
        author=author,
        description=description,
        language=original_language or language,
        publication_year=publication_year,
        work_slug=work_slug,
        edition_slug=edition_slug,
        edition_title=edition_title,
        cover_url=cover_url,
    )
    if work is None and work_slug:
        work, _ = Work.objects.get_or_create(
            slug=work_slug,
            defaults={
                "title": work_title,
                "author": author,
                "description": description,
                "original_language": original_language,
                "publication_year": publication_year,
                "cover_url": cover_url,
            },
        )
    elif work is None:
        work = Work.objects.create(slug=provisional_slug(), original_language=original_language)

    # A pinned value wins over whatever the work already holds.
    for field, value in (
        ("title", work_title),
        ("author", author),
        ("description", description),
        ("original_language", original_language),
        ("publication_year", publication_year),
        ("cover_url", cover_url),
    ):
        if value not in (None, ""):
            setattr(work, field, value)
    provenance = dict(work.metadata_provenance)
    provenance.update({name: PROVENANCE_USER for name in pinned})
    work.metadata_provenance = provenance
    work.save()

    edition = Edition.objects.create(
        slug=edition_slug or provisional_slug(),
        work=work,
        title=edition_title or work_title,
        author=author or work.author,
        language=language,
        edition_type=edition_type,
        cefr_level=cefr_level or None,
        source_file=source_file,
        status=Edition.Status.QUEUED,
    )

    from almonium_book_processor.catalog.tasks import process_book_pipeline

    transaction.on_commit(lambda: process_book_pipeline.delay(str(edition.id)))
    return edition


def create_library_ingest(
    *,
    suggestion_id: uuid.UUID,
    import_id: uuid.UUID,
    owner_id: uuid.UUID,
    title: str,
    author: str,
    description: str = "",
    language: str = "",
    publication_year: int | None = None,
) -> tuple[Edition, bool]:
    """Seed a public catalogue edition from the file behind a private import.

    The private text is never promoted in place: the owner's copy stays theirs,
    and the library gets a fresh edition that runs the whole public pipeline and
    waits for an editor's level, cover, and publication like any upload. The
    product API's suggestion id keys the call, so a repeat returns the edition
    it already made.
    """

    existing = Edition.objects.select_related("work").filter(external_job_id=suggestion_id).first()
    if existing is not None:
        return existing, False

    source = (
        Edition.objects.select_related("work")
        .filter(id=import_id, work__visibility=Work.Visibility.PRIVATE, work__owner_id=owner_id)
        .first()
    )
    if source is None or not source.source_file:
        raise LookupError("Private import not found.")

    with source.source_file.open("rb") as stream:
        copied = File(stream, name=Path(source.source_file.name).name)
        with transaction.atomic():
            edition = create_source_edition(
                source_file=copied,
                work_title=title,
                author=author,
                description=description,
                original_language=language,
                publication_year=publication_year,
                language=language,
            )
            edition.external_job_id = suggestion_id
            edition.save(update_fields=["external_job_id", "updated_at"])
    return edition, True


@transaction.atomic
def create_private_import(
    *,
    import_id: uuid.UUID,
    owner_id: uuid.UUID,
    owner_label: str,
    source_file: File,
    title: str = "",
    author: str = "",
    description: str = "",
    language: str = "",
    publication_year: int | None = None,
) -> Edition:
    """Create an opaque, user-owned edition without exposing a catalog slug.

    Bibliographic fields are optional: whatever the owner leaves blank is read
    from the file header after ingestion and refined by the metadata stage.
    """
    existing = Edition.objects.filter(id=import_id, work__owner_id=owner_id).first()
    if existing:
        return existing

    from almonium_book_processor.catalog.metadata import initial_provenance

    title, author = calm_title(title), calm_title(author)
    private_slug = f"private-{import_id}"
    work = Work.objects.create(
        slug=private_slug,
        title=title,
        author=author,
        description=description,
        original_language=language,
        publication_year=publication_year,
        visibility=Work.Visibility.PRIVATE,
        owner_id=owner_id,
        owner_label=owner_label,
        metadata_provenance=initial_provenance(
            title=title,
            author=author,
            description=description,
            language=language,
            publication_year=publication_year,
        ),
    )
    edition = Edition.objects.create(
        id=import_id,
        slug=private_slug,
        work=work,
        title=title,
        author=author,
        language=language,
        edition_type=Edition.EditionType.ORIGINAL,
        source_file=source_file,
        status=Edition.Status.QUEUED,
    )

    from almonium_book_processor.catalog.tasks import process_book_pipeline

    transaction.on_commit(lambda: process_book_pipeline.delay(str(edition.id)))
    return edition


@transaction.atomic
def persist_artifact(edition: Edition, artifact: BookArtifact, run: PipelineRun) -> None:
    # A canonical original roots the work's block tree: every generated
    # edition copies its block groups instead of inferring a correspondence.
    # The groups are minted here, at normalization, and survive a re-run for
    # every block id that survives, so the parallels built from the previous
    # normalization stay attached to the text they translate.
    canonical = edition.parallel_role == Edition.ParallelRole.CANONICAL
    previous_groups: dict[str, uuid.UUID] = {}
    if canonical:
        previous_groups = {
            block_id: group
            for block_id, group in edition.blocks.filter(align_group__isnull=False).values_list(
                "block_id", "align_group"
            )
        }

    edition.chapters.all().delete()
    edition.warnings.all().delete()

    chapter_numbers = sorted({block.chapter for block in artifact.blocks})
    chapters = {
        number: Chapter.objects.create(edition=edition, sequence=number)
        for number in chapter_numbers
    }
    block_rows: list[ContentBlock] = []
    for block in artifact.blocks:
        block_rows.append(
            ContentBlock(
                edition=edition,
                chapter=chapters[block.chapter],
                block_id=block.block_id,
                sequence=block.seq,
                block_type=block.type.value,
                text=block.text,
                sentences=[sentence.model_dump(mode="json") for sentence in block.sentences],
                source_ref=block.source_ref or "",
                attributes=block.attributes,
                align_group=(
                    (previous_groups.get(block.block_id) or uuid.uuid4()) if canonical else None
                ),
            )
        )
    ContentBlock.objects.bulk_create(block_rows, batch_size=1000)

    headings: dict[int, str] = {}
    for block in artifact.blocks:
        if block.type.value == "heading" and block.chapter not in headings:
            headings[block.chapter] = block.text[:500]
    for number, title in headings.items():
        chapters[number].title = title
    Chapter.objects.bulk_update(list(chapters.values()), ["title"])

    QAWarning.objects.bulk_create(
        [
            QAWarning(
                edition=edition,
                pipeline_run=run,
                code=warning.code,
                severity=ingestion_warning_severity(warning.code),
                message=warning.message,
                source_ref=warning.source_ref or "",
            )
            for warning in artifact.warnings
        ]
    )

    edition.schema_version = artifact.schema_version
    edition.source_sha256 = artifact.edition.source.sha256
    edition.word_count = sum(len(block.text.split()) for block in artifact.blocks)
    has_actionable_warnings = any(
        ingestion_warning_severity(warning.code) != IngestionWarningSeverity.INFO
        for warning in artifact.warnings
    )
    edition.status = (
        Edition.Status.READY
        if edition.work.visibility == Work.Visibility.PRIVATE
        else Edition.Status.REVIEW
        if has_actionable_warnings
        else Edition.Status.READY
    )
    edition.save(
        update_fields=[
            "schema_version",
            "source_sha256",
            "word_count",
            "status",
            "updated_at",
        ]
    )


@transaction.atomic
def complete_review(
    *, edition: Edition, reviewer: AbstractBaseUser, notes: str = ""
) -> ReviewDecision:
    """Record a review decision and let an edition proceed to the ready state."""

    if edition.status != Edition.Status.REVIEW:
        raise ValueError("Only editions awaiting review can be completed.")

    from almonium_book_processor.catalog.adaptation_quality import adaptation_quality

    quality = adaptation_quality(edition)
    if blocker := quality.get("adaptation_blocker"):
        raise ValueError(blocker)

    unresolved_warnings = edition.warnings.exclude(severity=QAWarning.Severity.INFO).filter(
        resolved_at=None
    )
    if unresolved_warnings.exists():
        raise ValueError("Resolve every review item before completing review.")

    actionable_warning_count = edition.warnings.exclude(severity=QAWarning.Severity.INFO).count()
    decision = ReviewDecision.objects.create(
        edition=edition,
        reviewer=reviewer,
        notes=notes,
        source_sha256=edition.source_sha256,
        actionable_warning_count=actionable_warning_count,
    )
    edition.status = Edition.Status.READY
    update_fields = ["status", "updated_at"]
    # The gate just proved every chapter sits at or below the generation
    # target on a current assessment, so a passing review is the editorial
    # statement that the text is at that level. Only a label an editor never
    # set is filled in; an explicit choice stays.
    if quality.get("adaptation_target") and not edition.cefr_level:
        edition.cefr_level = quality["adaptation_target"]
        edition.cefr_level_source = Edition.LevelSource.TARGET
        update_fields += ["cefr_level", "cefr_level_source"]
    edition.save(update_fields=update_fields)
    if quality.get("adaptation_target"):
        from almonium_book_processor.catalog.adaptation_floor import refresh_adaptation_floor

        refresh_adaptation_floor(edition.work)
    return decision


@transaction.atomic
def review_alignment_group(
    *, edition: Edition, group_id: uuid.UUID, reviewer: AbstractBaseUser, notes: str = ""
) -> AlignmentGroupReview:
    alignments = list(
        BlockAlignment.objects.filter(target_edition=edition, group_id=group_id).select_related(
            "source_block", "target_block"
        )
    )
    if not alignments:
        raise ValueError("This alignment group no longer exists.")
    source_ids = sorted({str(alignment.source_block_id) for alignment in alignments})
    target_ids = sorted({str(alignment.target_block_id) for alignment in alignments})
    review, _ = AlignmentGroupReview.objects.update_or_create(
        target_edition=edition,
        group_id=group_id,
        defaults={
            "reviewer": reviewer,
            "decision": AlignmentGroupReview.Decision.ACCEPTED,
            "source_block_ids": source_ids,
            "target_block_ids": target_ids,
            "notes": notes,
        },
    )
    edition.warnings.filter(
        code="alignment_low_confidence",
        block_id__in=target_ids,
        resolved_at=None,
    ).update(resolved_at=timezone.now(), resolved_by=reviewer)
    return review


@transaction.atomic
def review_alignment_chapter(
    *,
    edition: Edition,
    chapter: int,
    reviewer: AbstractBaseUser,
    notes: str,
) -> int:
    if not notes:
        raise ValueError("Add an audit note before accepting a chapter.")
    group_ids = list(
        BlockAlignment.objects.filter(
            target_edition=edition,
            target_block__chapter__sequence=chapter,
        )
        .values_list("group_id", flat=True)
        .distinct()
    )
    if not group_ids:
        raise ValueError("This chapter has no alignment groups to accept.")
    for group_id in group_ids:
        review_alignment_group(
            edition=edition,
            group_id=group_id,
            reviewer=reviewer,
            notes=notes,
        )
    return len(group_ids)


@transaction.atomic
def confirm_ai_alignment_groups(*, edition: Edition, reviewer: AbstractBaseUser) -> int:
    """Add one staff audit decision to every still-current AI-approved group."""

    current_group_ids = BlockAlignment.objects.filter(target_edition=edition).values_list(
        "group_id", flat=True
    )
    reviews = list(
        AlignmentGroupReview.objects.filter(
            target_edition=edition,
            group_id__in=current_group_ids,
            decision=AlignmentGroupReview.Decision.AI_ACCEPTED,
        )
    )
    now = timezone.now()
    for review in reviews:
        review.decision = AlignmentGroupReview.Decision.ACCEPTED
        review.reviewer = reviewer
        review.notes = f"{review.notes}\nBulk-confirmed from the AI-safe set.".strip()
        review.updated_at = now
    AlignmentGroupReview.objects.bulk_update(
        reviews,
        ["decision", "reviewer", "notes", "updated_at"],
        batch_size=500,
    )
    return len(reviews)


@transaction.atomic
def repair_alignment_group(
    *,
    edition: Edition,
    source_block_ids: list[uuid.UUID],
    target_block_ids: list[uuid.UUID],
    reviewer: AbstractBaseUser,
    notes: str = "",
) -> AlignmentGroupReview:
    source_edition = edition.inferred_alignment_source
    if source_edition is None:
        raise ValueError("This edition has no canonical text to align against.")
    if not source_block_ids or not target_block_ids:
        raise ValueError("Select at least one source block and one target block.")

    source_blocks = list(
        ContentBlock.objects.filter(
            id__in=source_block_ids,
            edition=source_edition,
        ).select_related("chapter")
    )
    target_blocks = list(
        ContentBlock.objects.filter(id__in=target_block_ids, edition=edition).select_related(
            "chapter"
        )
    )
    if len(source_blocks) != len(set(source_block_ids)):
        raise ValueError("One or more selected source blocks are invalid.")
    if len(target_blocks) != len(set(target_block_ids)):
        raise ValueError("One or more selected target blocks are invalid.")
    target_chapters = {block.chapter_id for block in target_blocks}
    if len(target_chapters) != 1:
        raise ValueError("Manual target blocks must belong to one chapter.")
    allowed_source_chapters = set(
        ChapterAlignment.objects.filter(
            target_edition=edition,
            target_chapter_id__in=target_chapters,
        ).values_list("source_chapter_id", flat=True)
    )
    if not allowed_source_chapters:
        target_sequence = target_blocks[0].chapter.sequence
        allowed_source_chapters = set(
            source_edition.chapters.filter(sequence=target_sequence).values_list("id", flat=True)
        )
    if any(block.chapter_id not in allowed_source_chapters for block in source_blocks):
        raise ValueError("Source blocks must belong to chapters mapped to the target chapter.")

    affected_group_ids = (
        BlockAlignment.objects.filter(target_edition=edition)
        .filter(Q(source_block_id__in=source_block_ids) | Q(target_block_id__in=target_block_ids))
        .values_list("group_id", flat=True)
    )
    BlockAlignment.objects.filter(
        target_edition=edition,
        group_id__in=list(affected_group_ids),
    ).delete()

    group_id = uuid.uuid4()
    BlockAlignment.objects.bulk_create(
        [
            BlockAlignment(
                source_edition=source_edition,
                target_edition=edition,
                source_block=source_block,
                target_block=target_block,
                group_id=group_id,
                confidence=1.0,
                strategy="human-reviewed-v1",
            )
            for source_block in source_blocks
            for target_block in target_blocks
        ]
    )
    review = AlignmentGroupReview.objects.create(
        target_edition=edition,
        group_id=group_id,
        reviewer=reviewer,
        decision=AlignmentGroupReview.Decision.REPAIRED,
        source_block_ids=sorted(str(block.id) for block in source_blocks),
        target_block_ids=sorted(str(block.id) for block in target_blocks),
        notes=notes,
    )
    edition.warnings.filter(
        code="alignment_low_confidence",
        block__in=target_blocks,
        resolved_at=None,
    ).update(resolved_at=timezone.now(), resolved_by=reviewer)
    return review


@transaction.atomic
def translate_coverage_gap(
    *,
    edition: Edition,
    source_block_id: uuid.UUID,
    target_chapter_sequence: int,
    translated_text: str,
    editor: AbstractBaseUser,
    notes: str = "",
) -> ContentBlock:
    """Create and align a manually translated target block for a source-only gap."""

    source_edition = edition.inferred_alignment_source
    if source_edition is None:
        raise ValueError("This edition has no canonical text to translate from.")
    translated_text = translated_text.strip()
    if not translated_text:
        raise ValueError("Enter the translated text.")

    source_block = (
        ContentBlock.objects.select_for_update()
        .select_related("chapter")
        .filter(id=source_block_id, edition=source_edition)
        .first()
    )
    if source_block is None:
        raise ValueError("The source block does not belong to the canonical edition.")
    if BlockAlignment.objects.filter(
        target_edition=edition,
        source_block=source_block,
    ).exists():
        raise ValueError("This source block is already aligned and is no longer a coverage gap.")

    target_chapter = edition.chapters.filter(sequence=target_chapter_sequence).first()
    if target_chapter is None:
        raise ValueError("The selected target chapter does not belong to this edition.")
    mapped_source_chapter_ids = set(
        ChapterAlignment.objects.filter(
            target_edition=edition,
            target_chapter=target_chapter,
        ).values_list("source_chapter_id", flat=True)
    )
    if not mapped_source_chapter_ids:
        mapped_source_chapter_ids = set(
            source_edition.chapters.filter(sequence=target_chapter.sequence).values_list(
                "id", flat=True
            )
        )
    if source_block.chapter_id not in mapped_source_chapter_ids:
        raise ValueError("The source block is not mapped to the selected target chapter.")

    target_blocks = list(
        ContentBlock.objects.select_for_update().filter(chapter=target_chapter).order_by("sequence")
    )
    neighboring_alignments = BlockAlignment.objects.filter(
        target_edition=edition,
        source_block__chapter_id=source_block.chapter_id,
        target_block__chapter=target_chapter,
    ).select_related("source_block", "target_block")
    preceding_sequences = [
        alignment.target_block.sequence
        for alignment in neighboring_alignments
        if alignment.source_block.sequence < source_block.sequence
    ]
    following_sequences = [
        alignment.target_block.sequence
        for alignment in neighboring_alignments
        if alignment.source_block.sequence > source_block.sequence
    ]
    if preceding_sequences:
        insertion_sequence = max(preceding_sequences) + 1
    elif following_sequences:
        insertion_sequence = min(following_sequences)
    else:
        insertion_sequence = len(target_blocks) + 1

    blocks_to_shift = [block for block in target_blocks if block.sequence >= insertion_sequence]
    temporary_sequence = max((block.sequence for block in target_blocks), default=0) + 1
    for index, block in enumerate(blocks_to_shift):
        ContentBlock.objects.filter(id=block.id).update(sequence=temporary_sequence + index)
    for block in blocks_to_shift:
        ContentBlock.objects.filter(id=block.id).update(sequence=block.sequence + 1)

    target_block = ContentBlock.objects.create(
        edition=edition,
        chapter=target_chapter,
        block_id=f"manual.{uuid.uuid4().hex}",
        sequence=insertion_sequence,
        block_type=source_block.block_type,
        text=translated_text,
        sentences=[],
        source_ref=f"manual-translation:{source_block.id}",
        attributes={
            "manual_translation": {
                "source_block_id": str(source_block.id),
                "editor_id": str(editor.pk),
            }
        },
    )
    group_id = uuid.uuid4()
    BlockAlignment.objects.create(
        source_edition=source_edition,
        target_edition=edition,
        source_block=source_block,
        target_block=target_block,
        group_id=group_id,
        confidence=1.0,
        strategy="human-translation-v1",
    )
    AlignmentGroupReview.objects.create(
        target_edition=edition,
        group_id=group_id,
        reviewer=editor,
        decision=AlignmentGroupReview.Decision.REPAIRED,
        source_block_ids=[str(source_block.id)],
        target_block_ids=[str(target_block.id)],
        notes=notes or "Manually translated a source-only coverage gap.",
    )
    edition.word_count = sum(
        len(text.split()) for text in edition.blocks.values_list("text", flat=True)
    )
    edition.save(update_fields=["word_count", "updated_at"])

    from almonium_book_processor.catalog.tasks import split_edition_sentences

    transaction.on_commit(lambda: split_edition_sentences.delay(str(edition.id)))
    return target_block


def _record_block_revision(
    *,
    edition: Edition,
    block: ContentBlock,
    revised_text: str,
    editor: AbstractBaseUser,
    notes: str = "",
) -> ContentBlockRevision:
    revised_text = revised_text.strip()
    if not revised_text and block.block_type not in {
        ContentBlock.BlockType.IMAGE,
        ContentBlock.BlockType.SEPARATOR,
    }:
        raise ValueError("Text blocks cannot be empty.")
    if revised_text == block.text:
        raise ValueError("The revised text is unchanged.")

    revision = ContentBlockRevision.objects.create(
        edition=edition,
        block=block,
        stable_block_id=block.block_id,
        editor=editor,
        previous_text=block.text,
        revised_text=revised_text,
        notes=notes,
    )
    block.text = revised_text
    block.sentences = []
    block.save(update_fields=["text", "sentences", "updated_at"])
    return revision


def _finish_text_revision(edition: Edition, changed_block_ids: set[uuid.UUID]) -> None:
    edition.word_count = sum(
        len(text.split()) for text in edition.blocks.values_list("text", flat=True)
    )
    edition.save(update_fields=["word_count", "updated_at"])
    edition.artifacts.filter(is_current=True).update(is_current=False)
    # Fidelity findings on a changed block are placed again by their own path,
    # not dropped: the one an editor applied should not silence its neighbours.
    edition.text_quality_findings.filter(
        status=TextQualityFinding.Status.OPEN,
        block_id__in=changed_block_ids,
    ).exclude(code__startswith="fidelity_").update(status=TextQualityFinding.Status.SUPERSEDED)

    from almonium_book_processor.catalog.tasks import refresh_edition_after_revision

    transaction.on_commit(lambda: refresh_edition_after_revision.delay(str(edition.id)))
    _requeue_analysis_after_commit(edition)


@transaction.atomic
def revise_block_text(
    *,
    edition: Edition,
    block_id: uuid.UUID,
    revised_text: str,
    editor: AbstractBaseUser,
    notes: str = "",
) -> ContentBlockRevision:
    block = ContentBlock.objects.select_for_update().filter(id=block_id, edition=edition).first()
    if block is None:
        raise ValueError("The target block does not belong to this edition.")
    revision = _record_block_revision(
        edition=edition,
        block=block,
        revised_text=revised_text,
        editor=editor,
        notes=notes,
    )
    _finish_text_revision(edition, {block.id})
    return revision


@transaction.atomic
def remove_block(
    *,
    edition: Edition,
    block_id: uuid.UUID,
    editor: AbstractBaseUser,
    notes: str = "",
) -> ContentBlockRevision:
    """Take a block out of the edition; the revision keeps its text for the audit trail.

    Findings on the block are superseded rather than left pointing at nothing,
    and a chapter emptied by the removal goes with it, so the reader never
    lands on a blank page.
    """

    block = (
        ContentBlock.objects.select_for_update()
        .select_related("chapter")
        .filter(id=block_id, edition=edition)
        .first()
    )
    if block is None:
        raise ValueError("The target block does not belong to this edition.")
    revision = ContentBlockRevision.objects.create(
        edition=edition,
        stable_block_id=block.block_id,
        editor=editor,
        previous_text=block.text,
        revised_text="",
        notes=notes or f"Removed block {block.block_id}.",
    )
    edition.text_quality_findings.filter(status=TextQualityFinding.Status.OPEN, block=block).update(
        status=TextQualityFinding.Status.SUPERSEDED
    )
    chapter = block.chapter
    block.delete()
    if not chapter.blocks.exists():
        chapter.delete()
    _finish_text_revision(edition, set())
    return revision


@transaction.atomic
def apply_text_quality_finding(
    *,
    edition: Edition,
    finding_id: uuid.UUID,
    replacement: str,
    reviewer: AbstractBaseUser,
    notes: str = "",
) -> ContentBlockRevision:
    finding = (
        TextQualityFinding.objects.select_for_update(of=("self",))
        .select_related("block")
        .filter(id=finding_id, edition=edition)
        .first()
    )
    if finding is None:
        raise ValueError("This source-text finding does not belong to the edition.")
    if finding.status != TextQualityFinding.Status.OPEN:
        raise ValueError("This source-text finding is no longer open.")
    if finding.block is None or finding.start_offset is None or finding.end_offset is None:
        raise ValueError("This finding requires manual block inspection rather than inline repair.")
    current = finding.block.text[finding.start_offset : finding.end_offset]
    if current != finding.original_text:
        raise ValueError("The block changed after this finding was generated; run source QA again.")
    verbatim = replacement.strip() == (finding.suggested_text or "").strip()
    revised_text = (
        finding.block.text[: finding.start_offset]
        + replacement
        + finding.block.text[finding.end_offset :]
    )
    revision = revise_block_text(
        edition=edition,
        block_id=finding.block_id,
        revised_text=revised_text,
        editor=reviewer,
        notes=notes or f"Applied source-QA finding {finding.code}.",
    )
    finding.status = TextQualityFinding.Status.APPLIED
    finding.suggested_text = replacement
    finding.reviewed_by = reviewer
    finding.reviewed_at = timezone.now()
    finding.save(
        update_fields=[
            "status",
            "suggested_text",
            "reviewed_by",
            "reviewed_at",
            "updated_at",
        ]
    )
    _after_fidelity_decision(edition, finding, verbatim=verbatim)
    return revision


def _after_fidelity_decision(
    edition: Edition, finding: TextQualityFinding, *, verbatim: bool = False
) -> None:
    """Applying or dismissing a fidelity finding can change whether the level is reached."""

    if not finding.code.startswith("fidelity_"):
        return
    from almonium_book_processor.catalog.adaptation_floor import refresh_adaptation_floor
    from almonium_book_processor.catalog.fidelity_audit import (
        carry_audit_forward,
        relocate_fidelity_findings,
    )

    if finding.status == TextQualityFinding.Status.APPLIED:
        relocate_fidelity_findings(edition, [finding.block_id])
        if verbatim:
            carry_audit_forward(edition, [finding])
    refresh_adaptation_floor(edition.work)


def _requeue_analysis_after_commit(edition: Edition) -> None:
    """Text just changed: keep the difficulty verdict if the change is a phrase, re-judge if not.

    Every text revision ends here, whether an editor typed it or applied a
    finding. Only an edition that has been judged before is touched: a fix
    never starts the first paid analysis of a book, and a private work or a
    parallel translation has no analysis to refresh. When a window changed by
    more than a phrase, the re-read reuses every validated window whose text
    did not move, so only the changed chapters are billed.

    The audit is not re-run here either. Its own suggestions carry it
    forward; a hand edit leaves it stale and the page says what a re-read
    would cost.
    """

    if (
        edition.work.visibility != Work.Visibility.PUBLIC
        or edition.is_parallel_translation
        or not edition.pipeline_runs.filter(stage=PipelineRun.Stage.CHAPTER_ANALYSIS).exists()
    ):
        return

    def refresh() -> None:
        from almonium_book_processor.catalog.chapter_analysis import (
            carry_analysis_forward,
            queue_analysis,
        )

        try:
            if carry_analysis_forward(edition) is None:
                queue_analysis(str(edition.id))
        except ValueError as error:
            logger.warning("Could not refresh chapter analysis for %s: %s", edition.id, error)

    transaction.on_commit(refresh)


def _fidelity_findings(edition: Edition, severities: list[str]):
    return (
        TextQualityFinding.objects.select_for_update(of=("self",))
        .select_related("block")
        .filter(
            edition=edition,
            status=TextQualityFinding.Status.OPEN,
            code__in=[f"fidelity_{severity}" for severity in severities],
        )
        .order_by("stable_block_id", "-start_offset")
    )


@transaction.atomic
def apply_fidelity_findings(
    *, edition: Edition, reviewer: AbstractBaseUser, severities: list[str]
) -> int:
    """Apply every open fidelity suggestion that can be placed in its block, one revision per block.

    Findings in one block are applied from the end of the block backwards so
    earlier offsets stay true; two that overlap are left open for a hand edit.
    """

    findings = [
        finding
        for finding in _fidelity_findings(edition, severities)
        if finding.can_apply and finding.suggested_text
    ]
    if not findings:
        raise ValueError("There is no fidelity suggestion that can be applied as it stands.")
    by_block: dict = {}
    for finding in findings:
        by_block.setdefault(finding.block_id, []).append(finding)
    blocks = {
        block.id: block
        for block in ContentBlock.objects.select_for_update().filter(
            edition=edition, id__in=list(by_block)
        )
    }
    reviewed_at = timezone.now()
    applied = 0
    for block_id, group in by_block.items():
        block = blocks[block_id]
        text = block.text
        cursor = len(text)
        notes = []
        for finding in group:  # highest offset first
            if finding.end_offset > cursor:
                continue  # overlaps one already applied; stays open
            if text[finding.start_offset : finding.end_offset] != finding.original_text:
                raise ValueError("The text changed after this audit; audit it again.")
            text = (
                text[: finding.start_offset] + finding.suggested_text + text[finding.end_offset :]
            )
            cursor = finding.start_offset
            notes.append(f"{finding.original_text!r} → {finding.suggested_text!r}")
            finding.status = TextQualityFinding.Status.APPLIED
            finding.reviewed_by = reviewer
            finding.reviewed_at = reviewed_at
            finding.save(update_fields=["status", "reviewed_by", "reviewed_at", "updated_at"])
            applied += 1
        if not notes:
            continue
        _record_block_revision(
            edition=edition,
            block=block,
            revised_text=text,
            editor=reviewer,
            notes="Applied fidelity audit suggestions: " + "; ".join(reversed(notes)),
        )
    _finish_text_revision(edition, {block_id for block_id, group in by_block.items()})
    from almonium_book_processor.catalog.adaptation_floor import refresh_adaptation_floor
    from almonium_book_processor.catalog.fidelity_audit import (
        carry_audit_forward,
        relocate_fidelity_findings,
    )

    relocate_fidelity_findings(edition, list(by_block))
    carry_audit_forward(
        edition, [f for group in by_block.values() for f in group if f.status == "applied"]
    )
    refresh_adaptation_floor(edition.work)
    return applied


@transaction.atomic
def dismiss_fidelity_findings(
    *, edition: Edition, reviewer: AbstractBaseUser, severities: list[str]
) -> int:
    """Record that the adapted wording keeps the author's meaning for every open finding named."""

    findings = list(_fidelity_findings(edition, severities))
    if not findings:
        raise ValueError("There is no open fidelity finding to dismiss.")
    reviewed_at = timezone.now()
    for finding in findings:
        finding.status = TextQualityFinding.Status.DISMISSED
        finding.reviewed_by = reviewer
        finding.reviewed_at = reviewed_at
        finding.save(update_fields=["status", "reviewed_by", "reviewed_at", "updated_at"])
    from almonium_book_processor.catalog.adaptation_floor import refresh_adaptation_floor

    refresh_adaptation_floor(edition.work)
    return len(findings)


@transaction.atomic
def apply_high_confidence_detached_initials(
    *, edition: Edition, reviewer: AbstractBaseUser
) -> list[ContentBlockRevision]:
    findings = list(
        TextQualityFinding.objects.select_for_update(of=("self",))
        .filter(
            edition=edition,
            status=TextQualityFinding.Status.OPEN,
            code="detached_initial",
            confidence__gte=BULK_DETACHED_INITIAL_MIN_CONFIDENCE,
            block__isnull=False,
            start_offset__isnull=False,
            end_offset__isnull=False,
        )
        .order_by("stable_block_id")
    )
    if not findings:
        raise ValueError("There are no high-confidence detached initials to approve.")

    block_ids = [finding.block_id for finding in findings]
    if len(block_ids) != len(set(block_ids)):
        raise ValueError("Multiple detached-initial findings target the same block; rescan first.")
    blocks = {
        block.id: block
        for block in ContentBlock.objects.select_for_update().filter(
            edition=edition,
            id__in=block_ids,
        )
    }
    for finding in findings:
        block = blocks.get(finding.block_id)
        if block is None:
            raise ValueError("A detached-initial finding no longer has a current block.")
        current = block.text[finding.start_offset : finding.end_offset]
        if current != finding.original_text:
            raise ValueError("The text changed after this scan; run source QA again.")
        if not finding.suggested_text:
            raise ValueError("A detached-initial finding has no proposed replacement.")

    reviewed_at = timezone.now()
    revisions = []
    for finding in findings:
        block = blocks[finding.block_id]
        revised_text = (
            block.text[: finding.start_offset]
            + finding.suggested_text
            + block.text[finding.end_offset :]
        )
        revisions.append(
            _record_block_revision(
                edition=edition,
                block=block,
                revised_text=revised_text,
                editor=reviewer,
                notes=(
                    "Bulk-approved high-confidence detached initial "
                    f"{finding.original_text!r} → {finding.suggested_text!r}."
                ),
            )
        )
        finding.status = TextQualityFinding.Status.APPLIED
        finding.reviewed_by = reviewer
        finding.reviewed_at = reviewed_at
        finding.save(update_fields=["status", "reviewed_by", "reviewed_at", "updated_at"])

    _finish_text_revision(edition, set(block_ids))
    return revisions


@transaction.atomic
def dismiss_text_quality_finding(
    *, edition: Edition, finding_id: uuid.UUID, reviewer: AbstractBaseUser
) -> TextQualityFinding:
    finding = (
        TextQualityFinding.objects.select_for_update()
        .filter(
            id=finding_id,
            edition=edition,
        )
        .first()
    )
    if finding is None:
        raise ValueError("This source-text finding does not belong to the edition.")
    if finding.status == TextQualityFinding.Status.OPEN:
        finding.status = TextQualityFinding.Status.DISMISSED
        finding.reviewed_by = reviewer
        finding.reviewed_at = timezone.now()
        finding.save(update_fields=["status", "reviewed_by", "reviewed_at", "updated_at"])
        _after_fidelity_decision(edition, finding)
    return finding


@transaction.atomic
def reopen_text_quality_finding(
    *, edition: Edition, finding_id: uuid.UUID, reviewer: AbstractBaseUser
) -> TextQualityFinding:
    """A dismissal is a decision, not a deletion: it can be taken back while the text stands."""

    finding = (
        TextQualityFinding.objects.select_for_update()
        .select_related("block")
        .filter(id=finding_id, edition=edition)
        .first()
    )
    if finding is None:
        raise ValueError("This finding does not belong to the edition.")
    if finding.status != TextQualityFinding.Status.DISMISSED:
        raise ValueError("Only a dismissed finding can be reopened.")
    if finding.block is None or (
        finding.start_offset is not None
        and finding.block.text[finding.start_offset : finding.end_offset] != finding.original_text
    ):
        raise ValueError("The block changed since this finding was made; audit again instead.")
    finding.status = TextQualityFinding.Status.OPEN
    finding.reviewed_by = reviewer
    finding.reviewed_at = timezone.now()
    finding.save(update_fields=["status", "reviewed_by", "reviewed_at", "updated_at"])
    _after_fidelity_decision(edition, finding)
    return finding


@transaction.atomic
def apply_finding_with_block_text(
    *,
    edition: Edition,
    finding_id: uuid.UUID,
    revised_text: str,
    reviewer: AbstractBaseUser,
    notes: str = "",
) -> ContentBlockRevision:
    """Close a finding whose span could not be placed by rewriting its block by hand."""

    finding = (
        TextQualityFinding.objects.select_for_update(of=("self",))
        .select_related("block")
        .filter(id=finding_id, edition=edition)
        .first()
    )
    if finding is None:
        raise ValueError("This finding does not belong to the edition.")
    if finding.status != TextQualityFinding.Status.OPEN or finding.block is None:
        raise ValueError("This finding is no longer open.")
    revision = revise_block_text(
        edition=edition,
        block_id=finding.block_id,
        revised_text=revised_text,
        editor=reviewer,
        notes=notes or f"Hand edit closing {finding.code} finding on {finding.stable_block_id}.",
    )
    finding.status = TextQualityFinding.Status.APPLIED
    finding.reviewed_by = reviewer
    finding.reviewed_at = timezone.now()
    finding.save(update_fields=["status", "reviewed_by", "reviewed_at", "updated_at"])
    _after_fidelity_decision(edition, finding, verbatim=False)
    return revision


@transaction.atomic
def resolve_review_warning(
    *, edition: Edition, warning_id: uuid.UUID, reviewer: AbstractBaseUser
) -> QAWarning:
    warning = edition.warnings.select_for_update().filter(id=warning_id).first()
    if warning is None:
        raise ValueError("This review item does not belong to the edition.")
    from almonium_book_processor.catalog.adaptation_quality import (
        DIFFICULTY_WARNING,
        adaptation_blocker,
    )

    if warning.code == DIFFICULTY_WARNING and (blocker := adaptation_blocker(edition)):
        raise ValueError(blocker)
    if warning.resolved_at is None:
        warning.resolved_at = timezone.now()
        warning.resolved_by = reviewer
        warning.save(update_fields=["resolved_at", "resolved_by", "updated_at"])
    return warning


@transaction.atomic
def resolve_review_warnings(*, edition: Edition, code: str, reviewer: AbstractBaseUser) -> int:
    """Resolve every open review item of one code; the count resolved.

    The difficulty gate keeps its own rule: its item clears only by a passing
    reassessment, never by hand.
    """

    from almonium_book_processor.catalog.adaptation_quality import (
        DIFFICULTY_WARNING,
        adaptation_blocker,
    )

    if not code:
        raise ValueError("Say which kind of review item to resolve.")
    if code == DIFFICULTY_WARNING and (blocker := adaptation_blocker(edition)):
        raise ValueError(blocker)
    return (
        edition.warnings.select_for_update()
        .filter(code=code, resolved_at=None)
        .exclude(severity=QAWarning.Severity.INFO)
        .update(resolved_at=timezone.now(), resolved_by=reviewer, updated_at=timezone.now())
    )


@transaction.atomic
def release_private_import(
    *, edition: Edition, reviewer: AbstractBaseUser, notes: str = ""
) -> ReviewDecision | None:
    """Release operator-corrected private content to its owner without publication."""

    if edition.work.visibility != Work.Visibility.PRIVATE:
        raise ValueError("Only private imports can use the owner release workflow.")
    if not edition.blocks.exists():
        raise ValueError("This import has no normalized content to release.")
    if edition.status not in {Edition.Status.FAILED, Edition.Status.REVIEW, Edition.Status.READY}:
        raise ValueError("Wait for processing to finish before releasing this import.")

    decision = None
    if edition.status != Edition.Status.READY:
        decision = ReviewDecision.objects.create(
            edition=edition,
            reviewer=reviewer,
            notes=notes,
            source_sha256=edition.source_sha256,
            actionable_warning_count=edition.warnings.exclude(
                severity=QAWarning.Severity.INFO
            ).count(),
        )
        edition.status = Edition.Status.READY
        edition.save(update_fields=["status", "updated_at"])

    from almonium_book_processor.catalog.tasks import report_private_import_available

    transaction.on_commit(lambda: report_private_import_available.delay(str(edition.id)))
    return decision


def _artifact_from_upload(upload: BinaryIO) -> BookArtifact:
    payload = upload.read()
    upload.seek(0)
    return BookArtifact.model_validate(migrate_artifact_payload(json.loads(payload)))


def _import_legacy_artifact(artifact: BookArtifact) -> Edition:
    metadata = artifact.edition
    work, created = Work.objects.get_or_create(
        slug=metadata.work_slug,
        defaults={
            "title": metadata.title,
            "author": metadata.author,
            "original_language": metadata.language,
        },
    )
    if not created and metadata.edition_type == Edition.EditionType.ORIGINAL:
        work.title = metadata.title
        work.author = metadata.author
        work.original_language = metadata.language
        work.save(update_fields=["title", "author", "original_language", "updated_at"])
    source_edition = None
    if metadata.source_edition_slug:
        source_edition = Edition.objects.filter(slug=metadata.source_edition_slug).first()

    defaults = {
        "work": work,
        "source_edition": source_edition,
        "title": metadata.title,
        "author": metadata.author,
        "language": metadata.language,
        "edition_type": metadata.edition_type,
        "cefr_level": metadata.cefr_level,
        "status": Edition.Status.PROCESSING,
        "source_sha256": metadata.source.sha256,
    }
    if source_edition is not None:
        # A generated artifact is block for block with its source.
        defaults["parallel_role"] = Edition.ParallelRole.PARALLEL
    edition, _ = Edition.objects.update_or_create(slug=metadata.edition_slug, defaults=defaults)
    idempotency_key = f"{metadata.source.sha256}:legacy-import:{artifact.processor_version}"
    run, _ = PipelineRun.objects.update_or_create(
        idempotency_key=idempotency_key,
        defaults={
            "edition": edition,
            "stage": PipelineRun.Stage.INGEST,
            "status": PipelineRun.Status.RUNNING,
            "processor_version": artifact.processor_version,
            "input_hash": metadata.source.sha256,
        },
    )
    persist_artifact(edition, artifact, run)
    run.status = PipelineRun.Status.SUCCEEDED
    run.progress = 100
    run.summary = {
        "source": "legacy_normalized_json",
        "blocks": len(artifact.blocks),
        "warnings": len(artifact.warnings),
    }
    run.save(update_fields=["status", "progress", "summary", "updated_at"])
    return edition


@transaction.atomic
def import_legacy_artifact(upload: BinaryIO) -> Edition:
    edition = _import_legacy_artifact(_artifact_from_upload(upload))
    from almonium_book_processor.catalog.tasks import process_normalized_edition

    transaction.on_commit(lambda: process_normalized_edition.delay(str(edition.id)))
    return edition


@transaction.atomic
def import_legacy_artifacts(uploads: Iterable[BinaryIO]) -> list[Edition]:
    artifacts = [_artifact_from_upload(upload) for upload in uploads]
    artifacts.sort(
        key=lambda artifact: artifact.edition.edition_type != Edition.EditionType.ORIGINAL
    )
    editions = [_import_legacy_artifact(artifact) for artifact in artifacts]

    by_slug = {edition.slug: edition for edition in editions}
    for artifact, edition in zip(artifacts, editions, strict=True):
        source_slug = artifact.edition.source_edition_slug
        if source_slug and edition.source_edition_id is None:
            edition.source_edition = (
                by_slug.get(source_slug) or Edition.objects.filter(slug=source_slug).first()
            )
            if edition.source_edition_id:
                edition.parallel_role = Edition.ParallelRole.PARALLEL
                edition.save(update_fields=["source_edition", "parallel_role", "updated_at"])
    from almonium_book_processor.catalog.tasks import process_normalized_edition

    for edition in editions:
        transaction.on_commit(
            lambda edition_id=str(edition.id): process_normalized_edition.delay(edition_id)
        )
    return editions
