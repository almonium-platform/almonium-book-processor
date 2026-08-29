from __future__ import annotations

import hashlib
import importlib.metadata
import json
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
    ChapterAlignment,
    ContentBlock,
    Edition,
    EditionArtifact,
    PipelineRun,
    QAWarning,
    TextQualityFinding,
    Work,
)
from almonium_book_processor.catalog.publication import publish_to_almonium
from almonium_book_processor.catalog.services import persist_artifact
from almonium_book_processor.ingest.source import ingest_source, source_format
from almonium_book_processor.processing.lexical import (
    LEXICAL_PROCESSOR_VERSION,
    LEXICAL_SCHEMA_VERSION,
    LexicalBlock,
    analyze_lexicon,
    lexical_runtime_signature,
)
from almonium_book_processor.processing.nlp import (
    AlignmentCandidate,
    aggregate_embeddings,
    align_embeddings,
    embed_texts,
    split_sentences,
)
from almonium_book_processor.processing.source_qa import (
    SOURCE_QA_PROCESSOR_VERSION,
    SOURCE_QA_SCHEMA_VERSION,
    SourceQABlock,
    analyze_source_quality,
)

logger = logging.getLogger(__name__)

ALIGNMENT_CANDIDATE_MIN_CONFIDENCE = 0.45
CHAPTER_ALIGNMENT_MIN_CONFIDENCE = 0.32
ALIGNMENT_REVIEW_CONFIDENCE = 0.72
ALIGNMENT_MIN_COVERAGE = 0.90
ALIGNMENT_WARNING_CODES = {
    "alignment_ai_uncertain",
    "alignment_chapter_low_confidence",
    "alignment_incomplete",
    "alignment_low_confidence",
}
ALIGNMENT_PROCESSOR_VERSION = f"{__version__}:hierarchical-v1"


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


def _edition_content_hash(edition: Edition) -> str:
    return _text_hash(
        *edition.blocks.order_by("chapter__sequence", "sequence").values_list("block_id", "text")
    )


def _finish_normalized_pipeline(edition: Edition) -> None:
    edition.refresh_from_db()
    has_review_items = (
        edition.warnings.exclude(severity=QAWarning.Severity.INFO).filter(resolved_at=None).exists()
    )
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
        for task, label in (
            (analyze_edition_lexicon, "lexical enrichment"),
            (analyze_edition_source_quality, "source-text QA"),
        ):
            try:
                task.delay(edition_id)
            except Exception:
                logger.exception("Could not queue %s for edition %s", label, edition.id)
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
    sentence_input_hash = _text_hash(
        edition.source_sha256,
        edition.language,
        spacy_model,
        _edition_content_hash(edition),
    )
    valid_sentence_hashes = [sentence_input_hash]
    if not edition.block_revisions.exists():
        valid_sentence_hashes.append(
            _text_hash(edition.source_sha256, edition.language, spacy_model)
        )
    if not edition.pipeline_runs.filter(
        stage=PipelineRun.Stage.SENTENCES,
        status=PipelineRun.Status.SUCCEEDED,
        input_hash__in=valid_sentence_hashes,
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
    input_hash = _text_hash(
        edition.source_sha256,
        edition.language,
        spacy_model,
        _edition_content_hash(edition),
    )
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
def analyze_edition_lexicon(edition_id: str) -> None:
    """Persist non-blocking lexical artifacts for any normalized edition."""

    edition = Edition.objects.get(id=edition_id)
    content_hash = _edition_content_hash(edition)
    runtime_signature = lexical_runtime_signature(edition.language)
    input_hash = _text_hash(
        content_hash,
        edition.language,
        json.dumps(runtime_signature, sort_keys=True),
        LEXICAL_PROCESSOR_VERSION,
    )
    idempotency_key = f"{edition.id}:{input_hash}:lexical:{LEXICAL_PROCESSOR_VERSION}"
    run, _ = PipelineRun.objects.get_or_create(
        idempotency_key=idempotency_key,
        defaults={
            "edition": edition,
            "stage": PipelineRun.Stage.LEXICAL,
            "processor_version": LEXICAL_PROCESSOR_VERSION,
            "input_hash": input_hash,
        },
    )
    expected_kinds = {
        EditionArtifact.Kind.LEXICAL_PROFILE,
        EditionArtifact.Kind.USEFUL_WORDS,
    }
    existing_kinds = set(
        edition.artifacts.filter(
            input_hash=input_hash,
            processor_version=LEXICAL_PROCESSOR_VERSION,
            kind__in=expected_kinds,
        ).values_list("kind", flat=True)
    )
    if run.status == PipelineRun.Status.SUCCEEDED and existing_kinds == expected_kinds:
        with transaction.atomic():
            edition.artifacts.filter(kind__in=expected_kinds, is_current=True).update(
                is_current=False
            )
            edition.artifacts.filter(
                input_hash=input_hash,
                processor_version=LEXICAL_PROCESSOR_VERSION,
                kind__in=expected_kinds,
            ).update(is_current=True)
        return

    run.status = PipelineRun.Status.RUNNING
    run.started_at = timezone.now()
    run.progress = 10
    run.error = ""
    run.save(update_fields=["status", "started_at", "progress", "error", "updated_at"])
    try:
        blocks = [
            LexicalBlock(
                block_id=block.block_id,
                chapter=block.chapter.sequence,
                text=block.text,
            )
            for block in edition.blocks.exclude(text="")
            .select_related("chapter")
            .order_by("chapter__sequence", "sequence")
        ]
        profile, useful_words = analyze_lexicon(blocks, edition.language)
        with transaction.atomic():
            edition.artifacts.filter(kind__in=expected_kinds, is_current=True).update(
                is_current=False
            )
            for kind, payload in (
                (EditionArtifact.Kind.LEXICAL_PROFILE, profile),
                (EditionArtifact.Kind.USEFUL_WORDS, useful_words),
            ):
                EditionArtifact.objects.update_or_create(
                    edition=edition,
                    kind=kind,
                    input_hash=input_hash,
                    processor_version=LEXICAL_PROCESSOR_VERSION,
                    defaults={
                        "pipeline_run": run,
                        "schema_version": LEXICAL_SCHEMA_VERSION,
                        "payload": payload,
                        "is_current": True,
                    },
                )
            run.status = PipelineRun.Status.SUCCEEDED
            run.progress = 100
            run.finished_at = timezone.now()
            run.summary = {
                "total_tokens": profile["total_tokens"],
                "distinct_lemmas": profile["distinct_lemmas"],
                "useful_words": len(useful_words["words"]),
                "runtime": runtime_signature,
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
        run.status = PipelineRun.Status.FAILED
        run.finished_at = timezone.now()
        run.error = str(error)[:10000]
        run.save(update_fields=["status", "finished_at", "error", "updated_at"])
        raise


@shared_task(acks_late=True)
def analyze_edition_source_quality(edition_id: str) -> None:
    """Persist conservative source-text findings without editing content."""

    edition = Edition.objects.get(id=edition_id)
    content_hash = _edition_content_hash(edition)
    wordfreq_version = importlib.metadata.version("wordfreq")
    input_hash = _text_hash(
        content_hash,
        edition.language,
        wordfreq_version,
        SOURCE_QA_PROCESSOR_VERSION,
    )
    idempotency_key = f"{edition.id}:{input_hash}:source-qa:{SOURCE_QA_PROCESSOR_VERSION}"
    run, _ = PipelineRun.objects.get_or_create(
        idempotency_key=idempotency_key,
        defaults={
            "edition": edition,
            "stage": PipelineRun.Stage.SOURCE_QA,
            "processor_version": SOURCE_QA_PROCESSOR_VERSION,
            "input_hash": input_hash,
        },
    )
    existing_artifact = edition.artifacts.filter(
        kind=EditionArtifact.Kind.SOURCE_QA,
        input_hash=input_hash,
        processor_version=SOURCE_QA_PROCESSOR_VERSION,
    ).first()
    if run.status == PipelineRun.Status.SUCCEEDED and existing_artifact:
        with transaction.atomic():
            edition.artifacts.filter(
                kind=EditionArtifact.Kind.SOURCE_QA,
                is_current=True,
            ).update(is_current=False)
            existing_artifact.is_current = True
            existing_artifact.save(update_fields=["is_current", "updated_at"])
            edition.text_quality_findings.filter(status=TextQualityFinding.Status.OPEN).exclude(
                input_hash=input_hash
            ).update(status=TextQualityFinding.Status.SUPERSEDED)
        return

    run.status = PipelineRun.Status.RUNNING
    run.started_at = timezone.now()
    run.progress = 10
    run.error = ""
    run.save(update_fields=["status", "started_at", "progress", "error", "updated_at"])
    try:
        blocks = [
            SourceQABlock(
                id=str(block.id),
                block_id=block.block_id,
                chapter=block.chapter.sequence,
                text=block.text,
            )
            for block in edition.blocks.exclude(text="")
            .select_related("chapter")
            .order_by("chapter__sequence", "sequence")
        ]
        findings = analyze_source_quality(blocks, edition.language)
        payload = {
            "schema_version": SOURCE_QA_SCHEMA_VERSION,
            "language": edition.language,
            "processor_version": SOURCE_QA_PROCESSOR_VERSION,
            "wordfreq_version": wordfreq_version,
            "finding_count": len(findings),
            "findings": [finding.payload() for finding in findings],
        }
        with transaction.atomic():
            edition.artifacts.filter(
                kind=EditionArtifact.Kind.SOURCE_QA,
                is_current=True,
            ).update(is_current=False)
            artifact, _ = EditionArtifact.objects.update_or_create(
                edition=edition,
                kind=EditionArtifact.Kind.SOURCE_QA,
                input_hash=input_hash,
                processor_version=SOURCE_QA_PROCESSOR_VERSION,
                defaults={
                    "pipeline_run": run,
                    "schema_version": SOURCE_QA_SCHEMA_VERSION,
                    "payload": payload,
                    "is_current": True,
                },
            )
            edition.text_quality_findings.filter(status=TextQualityFinding.Status.OPEN).exclude(
                input_hash=input_hash
            ).update(status=TextQualityFinding.Status.SUPERSEDED)
            blocks_by_id = {block.id: block for block in edition.blocks.all()}
            for finding in findings:
                TextQualityFinding.objects.update_or_create(
                    edition=edition,
                    input_hash=input_hash,
                    fingerprint=finding.fingerprint(),
                    defaults={
                        "pipeline_run": run,
                        "artifact": artifact,
                        "block": blocks_by_id.get(uuid.UUID(finding.block_id))
                        if finding.block_id
                        else None,
                        "stable_block_id": finding.stable_block_id,
                        "code": finding.code,
                        "start_offset": finding.start_offset,
                        "end_offset": finding.end_offset,
                        "original_text": finding.original_text,
                        "suggested_text": finding.suggested_text,
                        "confidence": finding.confidence,
                        "message": finding.message,
                        "evidence": finding.evidence,
                    },
                )
            run.status = PipelineRun.Status.SUCCEEDED
            run.progress = 100
            run.finished_at = timezone.now()
            run.summary = {
                "blocks": len(blocks),
                "findings": len(findings),
                "wordfreq_version": wordfreq_version,
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
        run.status = PipelineRun.Status.FAILED
        run.finished_at = timezone.now()
        run.error = str(error)[:10000]
        run.save(update_fields=["status", "finished_at", "error", "updated_at"])
        raise


@shared_task(acks_late=True)
def refresh_edition_after_revision(edition_id: str) -> None:
    """Rebuild text-dependent local artifacts after a human correction."""

    split_edition_sentences.run(edition_id)
    for task, label in (
        (analyze_edition_lexicon, "lexical analysis"),
        (analyze_edition_source_quality, "source-text QA"),
    ):
        try:
            task.run(edition_id)
        except Exception:
            logger.exception("Could not refresh %s for edition %s", label, edition_id)


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
        idempotency_key=f"{edition.id}:{input_hash}:align:{ALIGNMENT_PROCESSOR_VERSION}",
        defaults={
            "edition": edition,
            "stage": PipelineRun.Stage.ALIGN,
            "processor_version": ALIGNMENT_PROCESSOR_VERSION,
            "input_hash": input_hash,
        },
    )
    if run.status == PipelineRun.Status.SUCCEEDED:
        return

    run.status = PipelineRun.Status.RUNNING
    run.started_at = timezone.now()
    run.progress = 5
    run.error = ""
    run.save(update_fields=["status", "started_at", "progress", "error", "updated_at"])
    try:
        source_blocks = list(source_edition.blocks.select_related("chapter").exclude(text=""))
        target_blocks = list(edition.blocks.select_related("chapter").exclude(text=""))
        source_vectors = (
            embed_texts([block.text for block in source_blocks]) if source_blocks else []
        )
        run.progress = 35
        run.save(update_fields=["progress", "updated_at"])
        target_vectors = (
            embed_texts([block.text for block in target_blocks]) if target_blocks else []
        )
        run.progress = 65
        run.save(update_fields=["progress", "updated_at"])
        source_by_chapter: dict[int, list[int]] = {}
        target_by_chapter: dict[int, list[int]] = {}
        for index, block in enumerate(source_blocks):
            source_by_chapter.setdefault(block.chapter.sequence, []).append(index)
        for index, block in enumerate(target_blocks):
            target_by_chapter.setdefault(block.chapter.sequence, []).append(index)
        source_chapter_numbers = sorted(source_by_chapter)
        target_chapter_numbers = sorted(target_by_chapter)
        source_chapter_groups = [source_by_chapter[number] for number in source_chapter_numbers]
        target_chapter_groups = [target_by_chapter[number] for number in target_chapter_numbers]
        chapter_alignment_candidates = align_embeddings(
            aggregate_embeddings(source_vectors, source_chapter_groups),
            aggregate_embeddings(target_vectors, target_chapter_groups),
            source_lengths=[
                sum(len(source_blocks[index].text) for index in indices)
                for indices in source_chapter_groups
            ],
            target_lengths=[
                sum(len(target_blocks[index].text) for index in indices)
                for indices in target_chapter_groups
            ],
            minimum_confidence=CHAPTER_ALIGNMENT_MIN_CONFIDENCE,
            skip_penalty=0.08,
        )
        run.progress = 75
        run.save(update_fields=["progress", "updated_at"])
        candidates: list[AlignmentCandidate] = []
        block_candidates_by_chapter_group: list[
            tuple[AlignmentCandidate, list[AlignmentCandidate]]
        ] = []
        for chapter_candidate in chapter_alignment_candidates:
            source_indices = [
                block_index
                for chapter_index in chapter_candidate.source_indices
                for block_index in source_chapter_groups[chapter_index]
            ]
            target_indices = [
                block_index
                for chapter_index in chapter_candidate.target_indices
                for block_index in target_chapter_groups[chapter_index]
            ]
            local_candidates = align_embeddings(
                [source_vectors[index] for index in source_indices],
                [target_vectors[index] for index in target_indices],
                source_lengths=[len(source_blocks[index].text) for index in source_indices],
                target_lengths=[len(target_blocks[index].text) for index in target_indices],
                minimum_confidence=ALIGNMENT_CANDIDATE_MIN_CONFIDENCE,
            )
            global_candidates = [
                AlignmentCandidate(
                    source_indices=tuple(
                        source_indices[index] for index in candidate.source_indices
                    ),
                    target_indices=tuple(
                        target_indices[index] for index in candidate.target_indices
                    ),
                    confidence=candidate.confidence,
                )
                for candidate in local_candidates
            ]
            candidates.extend(global_candidates)
            block_candidates_by_chapter_group.append((chapter_candidate, global_candidates))
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
            run.progress = 85
            run.save(update_fields=["progress", "updated_at"])
            BlockAlignment.objects.filter(
                source_edition=source_edition,
                target_edition=edition,
            ).delete()
            ChapterAlignment.objects.filter(
                source_edition=source_edition,
                target_edition=edition,
            ).delete()
            edition.warnings.filter(code__in=ALIGNMENT_WARNING_CODES).delete()
            chapter_alignment_rows = []
            chapter_mapping_summary = []
            for chapter_candidate, _ in block_candidates_by_chapter_group:
                group_id = uuid.uuid4()
                mapped_source_numbers = [
                    source_chapter_numbers[index] for index in chapter_candidate.source_indices
                ]
                mapped_target_numbers = [
                    target_chapter_numbers[index] for index in chapter_candidate.target_indices
                ]
                chapter_mapping_summary.append(
                    {
                        "source_chapters": mapped_source_numbers,
                        "target_chapters": mapped_target_numbers,
                        "confidence": chapter_candidate.confidence,
                    }
                )
                for source_number in mapped_source_numbers:
                    for target_number in mapped_target_numbers:
                        chapter_alignment_rows.append(
                            ChapterAlignment(
                                source_edition=source_edition,
                                target_edition=edition,
                                source_chapter=source_blocks[
                                    source_by_chapter[source_number][0]
                                ].chapter,
                                target_chapter=target_blocks[
                                    target_by_chapter[target_number][0]
                                ].chapter,
                                group_id=group_id,
                                confidence=chapter_candidate.confidence,
                                strategy="multilingual-embedding-monotonic-chapters-v1",
                            )
                        )
            ChapterAlignment.objects.bulk_create(chapter_alignment_rows, batch_size=500)
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
            warnings.extend(
                QAWarning(
                    edition=edition,
                    pipeline_run=run,
                    code="alignment_chapter_low_confidence",
                    severity=QAWarning.Severity.WARNING,
                    message=(
                        "Chapter correspondence confidence is "
                        f"{chapter_candidate.confidence:.1%} for source chapters "
                        + ", ".join(
                            str(source_chapter_numbers[index])
                            for index in chapter_candidate.source_indices
                        )
                        + " "
                        "and target chapters "
                        + ", ".join(
                            str(target_chapter_numbers[index])
                            for index in chapter_candidate.target_indices
                        )
                        + "."
                    ),
                )
                for chapter_candidate in chapter_alignment_candidates
                if chapter_candidate.confidence < ALIGNMENT_REVIEW_CONFIDENCE
            )
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
            "chapter_groups": len(chapter_alignment_candidates),
            "chapter_mappings": chapter_mapping_summary,
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


@shared_task(acks_late=True)
def prepare_ai_alignment(edition_id: str) -> str:
    """Refresh hierarchical candidates and submit autonomous AI review."""

    from almonium_book_processor.catalog.ai_alignment import submit_alignment_batch

    align_edition_to_source.run(edition_id)
    ai_run = submit_alignment_batch(edition_id, tier="primary")
    if ai_run.status == ai_run.Status.SUBMITTED:
        poll_ai_alignment_batch.apply_async(
            args=[str(ai_run.id)], countdown=settings.OPENAI_BATCH_POLL_SECONDS
        )
    return str(ai_run.id)


@shared_task(bind=True, acks_late=True, max_retries=1500)
def poll_ai_alignment_batch(self, ai_run_id: str) -> None:
    from almonium_book_processor.ai.openai_provider import OpenAIBatchProvider
    from almonium_book_processor.catalog.ai_alignment import (
        complete_alignment_batch,
        submit_alignment_batch,
    )
    from almonium_book_processor.catalog.models import AIRun

    ai_run = AIRun.objects.select_related("model_configuration").get(id=ai_run_id)
    if ai_run.status in {AIRun.Status.SUCCEEDED, AIRun.Status.FAILED}:
        return
    try:
        provider = OpenAIBatchProvider()
        batch = provider.retrieve(ai_run.provider_request_id)
        ai_run.response_payload = {
            **ai_run.response_payload,
            "batch_status": batch.status,
            "request_counts": batch.request_counts.model_dump() if batch.request_counts else {},
        }
        ai_run.save(update_fields=["response_payload", "updated_at"])
        if batch.status == "completed":
            uncertain_group_ids = complete_alignment_batch(
                ai_run, provider.output_lines(batch.output_file_id)
            )
            if ai_run.request_payload["tier"] == "primary" and uncertain_group_ids:
                escalation = submit_alignment_batch(
                    str(ai_run.edition_id),
                    tier="escalation",
                    group_ids=uncertain_group_ids,
                )
                if escalation.status == AIRun.Status.SUBMITTED:
                    poll_ai_alignment_batch.apply_async(
                        args=[str(escalation.id)], countdown=settings.OPENAI_BATCH_POLL_SECONDS
                    )
            return
        if batch.status in {"failed", "expired", "cancelled"}:
            raise RuntimeError(f"OpenAI Batch ended with status {batch.status}")
    except Exception as error:
        if getattr(error, "status_code", None) in {429, 500, 502, 503, 504}:
            raise self.retry(countdown=settings.OPENAI_BATCH_POLL_SECONDS, exc=error) from error
        ai_run.status = AIRun.Status.FAILED
        ai_run.error = str(error)[:10000]
        ai_run.finished_at = timezone.now()
        ai_run.save(update_fields=["status", "error", "finished_at", "updated_at"])
        raise
    raise self.retry(countdown=settings.OPENAI_BATCH_POLL_SECONDS)
