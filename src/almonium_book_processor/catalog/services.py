from __future__ import annotations

import hashlib
from collections.abc import Iterable
from typing import BinaryIO

from django.core.files import File
from django.db import transaction

from almonium_book_processor.catalog.models import (
    Chapter,
    ContentBlock,
    Edition,
    PipelineRun,
    QAWarning,
    Work,
)
from almonium_book_processor.models import BookArtifact


def hash_uploaded_file(upload: BinaryIO) -> str:
    digest = hashlib.sha256()
    for chunk in iter(lambda: upload.read(1024 * 1024), b""):
        digest.update(chunk)
    upload.seek(0)
    return digest.hexdigest()


@transaction.atomic
def create_epub_edition(
    *,
    work_slug: str,
    work_title: str,
    author: str,
    original_language: str,
    edition_slug: str,
    edition_title: str,
    language: str,
    edition_type: str,
    source_file: File,
) -> Edition:
    work, _ = Work.objects.get_or_create(
        slug=work_slug,
        defaults={
            "title": work_title,
            "author": author,
            "original_language": original_language,
        },
    )
    edition = Edition.objects.create(
        slug=edition_slug,
        work=work,
        title=edition_title,
        author=author,
        language=language,
        edition_type=edition_type,
        source_file=source_file,
        status=Edition.Status.QUEUED,
    )

    from almonium_book_processor.catalog.tasks import process_epub_edition

    transaction.on_commit(lambda: process_epub_edition.delay(str(edition.id)))
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
                message=warning.message,
                source_ref=warning.source_ref or "",
            )
            for warning in artifact.warnings
        ]
    )

    edition.schema_version = artifact.schema_version
    edition.source_sha256 = artifact.edition.source.sha256
    edition.word_count = sum(len(block.text.split()) for block in artifact.blocks)
    edition.status = Edition.Status.REVIEW if artifact.warnings else Edition.Status.READY
    edition.save(
        update_fields=[
            "schema_version",
            "source_sha256",
            "word_count",
            "status",
            "updated_at",
        ]
    )


def _artifact_from_upload(upload: BinaryIO) -> BookArtifact:
    payload = upload.read()
    upload.seek(0)
    return BookArtifact.model_validate_json(payload)


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
            "cefr_target": metadata.cefr_target or "",
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
    return _import_legacy_artifact(_artifact_from_upload(upload))


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
    return editions
