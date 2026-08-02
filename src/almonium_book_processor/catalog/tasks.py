from __future__ import annotations

import hashlib
import tempfile
import uuid
from pathlib import Path

from celery import shared_task
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from almonium_book_processor import __version__
from almonium_book_processor.catalog.models import (
    BlockAlignment,
    ContentBlock,
    Edition,
    PipelineRun,
)
from almonium_book_processor.catalog.publication import publish_to_almonium
from almonium_book_processor.catalog.services import persist_artifact
from almonium_book_processor.ingest.source import ingest_source, source_format
from almonium_book_processor.processing.nlp import align_embeddings, embed_texts, split_sentences


def _copy_source_to_temporary_file(edition: Edition) -> tuple[Path, str]:
    digest = hashlib.sha256()
    suffix = Path(edition.source_file.name).suffix.lower()
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as temporary:
        with edition.source_file.open("rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(chunk)
                temporary.write(chunk)
        return Path(temporary.name), digest.hexdigest()


@shared_task(bind=True, autoretry_for=(), acks_late=True)
def process_source_edition(self, edition_id: str) -> None:
    edition = Edition.objects.select_related("work", "source_edition").get(id=edition_id)
    temporary_path, source_hash = _copy_source_to_temporary_file(edition)
    idempotency_key = f"{edition.id}:{source_hash}:ingest:{__version__}"
    run, _ = PipelineRun.objects.get_or_create(
        idempotency_key=idempotency_key,
        defaults={
            "edition": edition,
            "stage": PipelineRun.Stage.INGEST,
            "status": PipelineRun.Status.QUEUED,
            "processor_version": __version__,
            "input_hash": source_hash,
        },
    )
    if run.status == PipelineRun.Status.SUCCEEDED:
        temporary_path.unlink(missing_ok=True)
        return

    edition.status = Edition.Status.PROCESSING
    edition.source_sha256 = source_hash
    edition.save(update_fields=["status", "source_sha256", "updated_at"])
    run.status = PipelineRun.Status.RUNNING
    run.started_at = timezone.now()
    run.progress = 5
    run.error = ""
    run.save(update_fields=["status", "started_at", "progress", "error", "updated_at"])

    try:
        artifact = ingest_source(
            temporary_path,
            edition_slug=edition.slug,
            work_slug=edition.work.slug,
            title=edition.title,
            author=edition.author,
            language=edition.language,
            edition_type=edition.edition_type,
            source_edition_slug=edition.source_edition.slug if edition.source_edition else None,
            cefr_target=edition.cefr_target or None,
        )
        with transaction.atomic():
            persist_artifact(edition, artifact, run)
            run.status = PipelineRun.Status.SUCCEEDED
            run.progress = 100
            run.finished_at = timezone.now()
            run.summary = {
                "celery_task_id": self.request.id,
                "source_format": source_format(temporary_path),
                "blocks": len(artifact.blocks),
                "warnings": len(artifact.warnings),
            }
            run.save(
                update_fields=[
                    "status",
                    "progress",
                    "finished_at",
                    "summary",
                    "updated_at",
                ]
            )
    except Exception as error:
        edition.status = Edition.Status.FAILED
        edition.save(update_fields=["status", "updated_at"])
        run.status = PipelineRun.Status.FAILED
        run.finished_at = timezone.now()
        run.error = str(error)[:10000]
        run.save(update_fields=["status", "finished_at", "error", "updated_at"])
        raise
    finally:
        temporary_path.unlink(missing_ok=True)


def _text_hash(*values: str) -> str:
    digest = hashlib.sha256()
    for value in values:
        digest.update(value.encode())
        digest.update(b"\0")
    return digest.hexdigest()


@shared_task(acks_late=True)
def publish_edition(edition_id: str) -> None:
    edition = Edition.objects.select_related("work", "source_edition").get(id=edition_id)
    if edition.status not in {Edition.Status.READY, Edition.Status.PUBLISHED}:
        raise ValueError("Only ready editions can be published.")
    input_hash = _text_hash(edition.source_sha256, edition.slug)
    run, _ = PipelineRun.objects.get_or_create(
        idempotency_key=f"{edition.id}:{input_hash}:publish:almonium-v1",
        defaults={
            "edition": edition,
            "stage": PipelineRun.Stage.PUBLISH,
            "processor_version": __version__,
            "input_hash": input_hash,
        },
    )
    if run.status == PipelineRun.Status.SUCCEEDED:
        return
    run.status = PipelineRun.Status.RUNNING
    run.started_at = timezone.now()
    run.error = ""
    run.save(update_fields=["status", "started_at", "error", "updated_at"])
    try:
        book_id = publish_to_almonium(edition)
        edition.published_book_id = book_id
        edition.status = Edition.Status.PUBLISHED
        edition.published_at = timezone.now()
        edition.save(update_fields=["published_book_id", "status", "published_at", "updated_at"])
        run.status = PipelineRun.Status.SUCCEEDED
        run.progress = 100
        run.finished_at = timezone.now()
        run.summary = {"almonium_book_id": book_id}
        run.save(update_fields=["status", "progress", "finished_at", "summary", "updated_at"])
    except Exception as error:
        run.status = PipelineRun.Status.FAILED
        run.finished_at = timezone.now()
        run.error = str(error)[:10000]
        run.save(update_fields=["status", "finished_at", "error", "updated_at"])
        raise


@shared_task(acks_late=True)
def split_edition_sentences(edition_id: str) -> None:
    edition = Edition.objects.get(id=edition_id)
    spacy_model = settings.NLP_SPACY_MODELS.get(edition.language, "blank")
    input_hash = _text_hash(edition.source_sha256, edition.language, spacy_model)
    run, _ = PipelineRun.objects.get_or_create(
        idempotency_key=f"{edition.id}:{input_hash}:sentences:{__version__}",
        defaults={
            "edition": edition,
            "stage": PipelineRun.Stage.SENTENCES,
            "processor_version": __version__,
            "input_hash": input_hash,
        },
    )
    if run.status == PipelineRun.Status.SUCCEEDED:
        return

    run.status = PipelineRun.Status.RUNNING
    run.started_at = timezone.now()
    run.error = ""
    run.save(update_fields=["status", "started_at", "error", "updated_at"])
    try:
        blocks = list(edition.blocks.exclude(text=""))
        sentence_count = 0
        updated_at = timezone.now()
        for block in blocks:
            offset = 0
            spans = []
            for sequence, sentence in enumerate(
                split_sentences(block.text, edition.language), start=1
            ):
                start = block.text.find(sentence, offset)
                if start < 0:
                    start = offset
                end = start + len(sentence)
                spans.append({"id": f"{block.block_id}.s{sequence}", "start": start, "end": end})
                sentence_count += 1
                offset = end
            block.sentences = spans
            block.updated_at = updated_at
        ContentBlock.objects.bulk_update(blocks, ["sentences", "updated_at"], batch_size=1000)
        run.status = PipelineRun.Status.SUCCEEDED
        run.progress = 100
        run.finished_at = timezone.now()
        run.summary = {
            "blocks": len(blocks),
            "sentences": sentence_count,
            "spacy_model": spacy_model,
        }
        run.save(update_fields=["status", "progress", "finished_at", "summary", "updated_at"])
    except Exception as error:
        run.status = PipelineRun.Status.FAILED
        run.finished_at = timezone.now()
        run.error = str(error)[:10000]
        run.save(update_fields=["status", "finished_at", "error", "updated_at"])
        raise


@shared_task(acks_late=True)
def align_edition_to_source(edition_id: str) -> None:
    edition = Edition.objects.select_related("source_edition").get(id=edition_id)
    if edition.source_edition is None:
        raise ValueError("A source edition is required for alignment")

    source_edition = edition.source_edition
    input_hash = _text_hash(
        source_edition.source_sha256,
        edition.source_sha256,
        settings.NLP_EMBEDDING_MODEL,
    )
    run, _ = PipelineRun.objects.get_or_create(
        idempotency_key=f"{edition.id}:{input_hash}:align:{__version__}",
        defaults={
            "edition": edition,
            "stage": PipelineRun.Stage.ALIGN,
            "processor_version": __version__,
            "input_hash": input_hash,
        },
    )
    if run.status == PipelineRun.Status.SUCCEEDED:
        return

    run.status = PipelineRun.Status.RUNNING
    run.started_at = timezone.now()
    run.error = ""
    run.save(update_fields=["status", "started_at", "error", "updated_at"])
    try:
        source_blocks = list(source_edition.blocks.exclude(text=""))
        target_blocks = list(edition.blocks.exclude(text=""))
        source_vectors = embed_texts([block.text for block in source_blocks])
        target_vectors = embed_texts([block.text for block in target_blocks])
        candidates = align_embeddings(source_vectors, target_vectors)
        with transaction.atomic():
            BlockAlignment.objects.filter(
                source_edition=source_edition,
                target_edition=edition,
            ).delete()
            BlockAlignment.objects.bulk_create(
                [
                    BlockAlignment(
                        source_edition=source_edition,
                        target_edition=edition,
                        source_block=source_blocks[candidate.source_index],
                        target_block=target_blocks[candidate.target_index],
                        group_id=uuid.uuid4(),
                        confidence=candidate.confidence,
                        strategy="multilingual-embedding-monotonic-v1",
                    )
                    for candidate in candidates
                ],
                batch_size=1000,
            )
        run.status = PipelineRun.Status.SUCCEEDED
        run.progress = 100
        run.finished_at = timezone.now()
        run.confidence = (
            sum(candidate.confidence for candidate in candidates) / len(candidates)
            if candidates
            else 0.0
        )
        run.summary = {
            "source_blocks": len(source_blocks),
            "target_blocks": len(target_blocks),
            "aligned_pairs": len(candidates),
            "embedding_model": settings.NLP_EMBEDDING_MODEL,
        }
        run.save(
            update_fields=[
                "status",
                "progress",
                "finished_at",
                "confidence",
                "summary",
                "updated_at",
            ]
        )
    except Exception as error:
        run.status = PipelineRun.Status.FAILED
        run.finished_at = timezone.now()
        run.error = str(error)[:10000]
        run.save(update_fields=["status", "finished_at", "error", "updated_at"])
        raise
