from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Iterable
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
    Work,
)
from almonium_book_processor.models import (
    BookArtifact,
    IngestionWarningSeverity,
    ingestion_warning_severity,
)


def hash_uploaded_file(upload: BinaryIO) -> str:
    digest = hashlib.sha256()
    for chunk in iter(lambda: upload.read(1024 * 1024), b""):
        digest.update(chunk)
    upload.seek(0)
    return digest.hexdigest()


@transaction.atomic
def create_source_edition(
    *,
    work_slug: str,
    work_title: str,
    author: str,
    description: str,
    original_language: str,
    publication_year: int,
    cover_url: str,
    edition_slug: str,
    edition_title: str,
    language: str,
    edition_type: str,
    source_edition: Edition | None,
    cefr_level: str,
    source_file: File,
) -> Edition:
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
    work.title = work_title
    work.author = author
    work.description = description
    work.original_language = original_language
    work.publication_year = publication_year
    if cover_url:
        work.cover_url = cover_url
    work.save()
    edition = Edition.objects.create(
        slug=edition_slug,
        work=work,
        title=edition_title,
        author=author,
        language=language,
        edition_type=edition_type,
        source_edition=source_edition,
        cefr_level=cefr_level,
        source_file=source_file,
        status=Edition.Status.QUEUED,
    )

    from almonium_book_processor.catalog.tasks import process_book_pipeline

    transaction.on_commit(lambda: process_book_pipeline.delay(str(edition.id)))
    return edition


@transaction.atomic
def create_private_import(
    *,
    import_id: uuid.UUID,
    owner_id: uuid.UUID,
    owner_label: str,
    title: str,
    author: str,
    description: str,
    language: str,
    publication_year: int | None,
    source_file: File,
) -> Edition:
    """Create an opaque, user-owned edition without exposing a catalog slug."""
    existing = Edition.objects.filter(id=import_id, work__owner_id=owner_id).first()
    if existing:
        return existing

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
    edition.save(update_fields=["status", "updated_at"])
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
def repair_alignment_group(
    *,
    edition: Edition,
    source_block_ids: list[uuid.UUID],
    target_block_ids: list[uuid.UUID],
    reviewer: AbstractBaseUser,
    notes: str = "",
) -> AlignmentGroupReview:
    if edition.source_edition_id is None:
        raise ValueError("This edition has no source edition to align.")
    if not source_block_ids or not target_block_ids:
        raise ValueError("Select at least one source block and one target block.")

    source_blocks = list(
        ContentBlock.objects.filter(
            id__in=source_block_ids,
            edition_id=edition.source_edition_id,
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
            edition.source_edition.chapters.filter(sequence=target_sequence).values_list(
                "id", flat=True
            )
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
                source_edition_id=edition.source_edition_id,
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
def revise_target_block(
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
    edition.word_count = sum(
        len(text.split()) for text in edition.blocks.values_list("text", flat=True)
    )
    edition.save(update_fields=["word_count", "updated_at"])

    from almonium_book_processor.catalog.tasks import split_edition_sentences

    transaction.on_commit(lambda: split_edition_sentences.delay(str(edition.id)))
    return revision


@transaction.atomic
def resolve_review_warning(
    *, edition: Edition, warning_id: uuid.UUID, reviewer: AbstractBaseUser
) -> QAWarning:
    warning = edition.warnings.select_for_update().filter(id=warning_id).first()
    if warning is None:
        raise ValueError("This review item does not belong to the edition.")
    if warning.resolved_at is None:
        warning.resolved_at = timezone.now()
        warning.resolved_by = reviewer
        warning.save(update_fields=["resolved_at", "resolved_by", "updated_at"])
    return warning


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

    edition, _ = Edition.objects.update_or_create(
        slug=metadata.edition_slug,
        defaults={
            "work": work,
            "source_edition": source_edition,
            "title": metadata.title,
            "author": metadata.author,
            "language": metadata.language,
            "edition_type": metadata.edition_type,
            "cefr_level": metadata.cefr_level,
            "status": Edition.Status.PROCESSING,
            "source_sha256": metadata.source.sha256,
        },
    )
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
                edition.save(update_fields=["source_edition", "updated_at"])
    from almonium_book_processor.catalog.tasks import process_normalized_edition

    for edition in editions:
        transaction.on_commit(
            lambda edition_id=str(edition.id): process_normalized_edition.delay(edition_id)
        )
    return editions
