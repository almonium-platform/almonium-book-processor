from __future__ import annotations

import hashlib
import logging
import tempfile
import uuid
from pathlib import Path

from celery import shared_task
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from almonium_book_processor import __version__
from almonium_book_processor.catalog.import_events import send_private_import_event
from almonium_book_processor.catalog.models import (
    BlockAlignment,
    ContentBlock,
    Edition,
    PipelineRun,
    QAWarning,
    Work,
)
from almonium_book_processor.catalog.publication import publish_to_almonium
from almonium_book_processor.catalog.services import persist_artifact
from almonium_book_processor.ingest.source import ingest_source, source_format
from almonium_book_processor.processing.nlp import (
    AlignmentCandidate,
    align_embeddings,
    embed_texts,
    split_sentences,
)

logger = logging.getLogger(__name__)

ALIGNMENT_CANDIDATE_MIN_CONFIDENCE = 0.45
ALIGNMENT_REVIEW_CONFIDENCE = 0.72
ALIGNMENT_MIN_COVERAGE = 0.90
ALIGNMENT_WARNING_CODES = {"alignment_incomplete", "alignment_low_confidence"}


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
    if edition.work.visibility == edition.work.Visibility.PRIVATE:
        try:
            send_private_import_event(edition, progress=run.progress)
        except Exception:
            logger.exception("Could not report processing state for private import %s", edition.id)

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
            cefr_level=edition.cefr_level,
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
        if edition.work.visibility == edition.work.Visibility.PRIVATE:
            try:
                send_private_import_event(edition, progress=run.progress, error=run.error)
            except Exception:
                logger.exception("Could not report failure for private import %s", edition.id)
        raise
    finally:
        temporary_path.unlink(missing_ok=True)


def _text_hash(*values: object) -> str:
    digest = hashlib.sha256()
    for value in values:
        digest.update(str(value).encode())
        digest.update(b"\0")
    return digest.hexdigest()


def _finish_normalized_pipeline(edition: Edition) -> None:
    edition.refresh_from_db()
    has_review_items = edition.warnings.exclude(severity=QAWarning.Severity.INFO).exists()
    edition.status = (
        Edition.Status.READY
        if edition.work.visibility == Work.Visibility.PRIVATE
        else Edition.Status.REVIEW
        if has_review_items
        else Edition.Status.READY
    )
    edition.save(update_fields=["status", "updated_at"])


@shared_task(bind=True, acks_late=True)
def process_book_pipeline(self, edition_id: str) -> None:
    """Ingest a source and continue through the credential-free NLP stages."""

    try:
        process_source_edition.run(edition_id)
        process_normalized_edition.run(edition_id)
    except Exception:
        logger.exception("Book pipeline failed for edition %s", edition_id)
        raise


@shared_task(bind=True, acks_late=True)
def process_normalized_edition(self, edition_id: str) -> None:
    """Split sentences, align derived editions, and apply cheap QA gates."""

    edition = Edition.objects.select_related("work", "source_edition").get(id=edition_id)
    edition.status = Edition.Status.PROCESSING
    edition.save(update_fields=["status", "updated_at"])
    try:
        if edition.source_edition_id:
            if not edition.source_edition.blocks.exists():
                raise ValueError("The source edition has no normalized blocks to align")
            split_edition_sentences.run(str(edition.source_edition_id))
        split_edition_sentences.run(edition_id)
        if edition.source_edition_id:
            align_edition_to_source.run(edition_id)
        _finish_normalized_pipeline(edition)
        edition.refresh_from_db()
        if edition.work.visibility == Work.Visibility.PRIVATE:
            try:
                send_private_import_event(edition, progress=100)
            except Exception:
                logger.exception("Could not report completion for private import %s", edition.id)
    except Exception as error:
        edition.status = Edition.Status.FAILED
        edition.save(update_fields=["status", "updated_at"])
        if edition.work.visibility == Work.Visibility.PRIVATE:
            try:
                send_private_import_event(edition, progress=0, error=str(error)[:10000])
            except Exception:
                logger.exception("Could not report NLP failure for private import %s", edition.id)
        raise


@shared_task(acks_late=True)
def publish_edition(edition_id: str) -> None:
    edition = Edition.objects.select_related("work", "source_edition").get(id=edition_id)
    if edition.work.visibility != edition.work.Visibility.PUBLIC:
        raise ValueError("Private imports cannot be published to the public catalog")
    if edition.status not in {Edition.Status.READY, Edition.Status.PUBLISHED}:
        raise ValueError("Only ready editions can be published.")
    if edition.cefr_level is None:
        raise ValueError("A CEFR level is required before publication.")
    if edition.work.publication_year is None:
        raise ValueError("A publication year is required before publication.")
    spacy_model = settings.NLP_SPACY_MODELS.get(edition.language, "blank")
    sentence_input_hash = _text_hash(edition.source_sha256, edition.language, spacy_model)
    if not edition.pipeline_runs.filter(
        stage=PipelineRun.Stage.SENTENCES,
        status=PipelineRun.Status.SUCCEEDED,
        input_hash=sentence_input_hash,
    ).exists():
        raise ValueError("Current sentence splitting must succeed before publication.")
    if edition.source_edition_id:
        alignment_input_hash = _text_hash(
            edition.source_edition.source_sha256,
            edition.source_sha256,
            settings.NLP_EMBEDDING_MODEL,
        )
        if not edition.pipeline_runs.filter(
            stage=PipelineRun.Stage.ALIGN,
            status=PipelineRun.Status.SUCCEEDED,
            input_hash=alignment_input_hash,
        ).exists():
            raise ValueError("Current source alignment must succeed before publication.")
    input_hash = _text_hash(
        edition.source_sha256,
        edition.slug,
        edition.work.slug,
        edition.title,
        edition.author,
        edition.work.original_language,
        edition.language,
        edition.edition_type,
        edition.source_edition.slug if edition.source_edition else None,
        edition.translator,
        edition.work.publication_year,
        edition.work.cover_url,
        edition.cefr_level,
        edition.word_count,
    )
    run, _ = PipelineRun.objects.get_or_create(
        idempotency_key=f"{edition.id}:{input_hash}:publish:almonium-v2",
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


@shared_task(
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_kwargs={"max_retries": 5},
)
def report_private_import_available(edition_id: str) -> None:
    edition = Edition.objects.select_related("work").get(id=edition_id)
    if edition.work.visibility != edition.work.Visibility.PRIVATE:
        raise ValueError("Only private imports have owner availability callbacks.")
    if edition.status != Edition.Status.READY or not edition.blocks.exists():
        raise ValueError("Only private imports with available content can be released.")
    send_private_import_event(edition, progress=100)


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
        source_vectors = (
            embed_texts([block.text for block in source_blocks]) if source_blocks else []
        )
        target_vectors = (
            embed_texts([block.text for block in target_blocks]) if target_blocks else []
        )
        source_by_chapter: dict[int, list[int]] = {}
        target_by_chapter: dict[int, list[int]] = {}
        for index, block in enumerate(source_blocks):
            source_by_chapter.setdefault(block.chapter.sequence, []).append(index)
        for index, block in enumerate(target_blocks):
            target_by_chapter.setdefault(block.chapter.sequence, []).append(index)
        common_chapters = sorted(source_by_chapter.keys() & target_by_chapter.keys())
        candidates: list[AlignmentCandidate] = []
        for chapter in common_chapters:
            source_indices = source_by_chapter[chapter]
            target_indices = target_by_chapter[chapter]
            chapter_candidates = align_embeddings(
                [source_vectors[index] for index in source_indices],
                [target_vectors[index] for index in target_indices],
                source_lengths=[len(source_blocks[index].text) for index in source_indices],
                target_lengths=[len(target_blocks[index].text) for index in target_indices],
                minimum_confidence=ALIGNMENT_CANDIDATE_MIN_CONFIDENCE,
            )
            candidates.extend(
                AlignmentCandidate(
                    source_indices=tuple(
                        source_indices[index] for index in candidate.source_indices
                    ),
                    target_indices=tuple(
                        target_indices[index] for index in candidate.target_indices
                    ),
                    confidence=candidate.confidence,
                )
                for candidate in chapter_candidates
            )
        matched_source_indices = {
            index for candidate in candidates for index in candidate.source_indices
        }
        matched_target_indices = {
            index for candidate in candidates for index in candidate.target_indices
        }
        source_coverage = len(matched_source_indices) / len(source_blocks) if source_blocks else 0.0
        target_coverage = len(matched_target_indices) / len(target_blocks) if target_blocks else 0.0
        low_confidence = [
            candidate
            for candidate in candidates
            if candidate.confidence < ALIGNMENT_REVIEW_CONFIDENCE
        ]
        with transaction.atomic():
            BlockAlignment.objects.filter(
                source_edition=source_edition,
                target_edition=edition,
            ).delete()
            edition.warnings.filter(code__in=ALIGNMENT_WARNING_CODES).delete()
            alignment_rows = []
            for candidate in candidates:
                group_id = uuid.uuid4()
                for source_index in candidate.source_indices:
                    for target_index in candidate.target_indices:
                        alignment_rows.append(
                            BlockAlignment(
                                source_edition=source_edition,
                                target_edition=edition,
                                source_block=source_blocks[source_index],
                                target_block=target_blocks[target_index],
                                group_id=group_id,
                                confidence=candidate.confidence,
                                strategy="multilingual-embedding-monotonic-v2",
                            )
                        )
            BlockAlignment.objects.bulk_create(alignment_rows, batch_size=1000)
            warnings = [
                QAWarning(
                    edition=edition,
                    pipeline_run=run,
                    block=target_blocks[candidate.target_index],
                    code="alignment_low_confidence",
                    severity=QAWarning.Severity.WARNING,
                    message=(
                        "Automatic alignment confidence is "
                        f"{candidate.confidence:.1%}; review this alignment group."
                    ),
                    source_ref=target_blocks[candidate.target_index].source_ref,
                )
                for candidate in low_confidence
            ]
            if source_coverage < ALIGNMENT_MIN_COVERAGE or target_coverage < ALIGNMENT_MIN_COVERAGE:
                warnings.append(
                    QAWarning(
                        edition=edition,
                        pipeline_run=run,
                        code="alignment_incomplete",
                        severity=QAWarning.Severity.WARNING,
                        message=(
                            f"Automatic alignment covered {source_coverage:.1%} of source blocks "
                            f"and {target_coverage:.1%} of target blocks."
                        ),
                    )
                )
            QAWarning.objects.bulk_create(warnings, batch_size=1000)
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
            "common_chapters": len(common_chapters),
            "source_only_chapters": len(source_by_chapter.keys() - target_by_chapter.keys()),
            "target_only_chapters": len(target_by_chapter.keys() - source_by_chapter.keys()),
            "alignment_groups": len(candidates),
            "alignment_rows": len(alignment_rows),
            "source_coverage": source_coverage,
            "target_coverage": target_coverage,
            "low_confidence_groups": len(low_confidence),
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
