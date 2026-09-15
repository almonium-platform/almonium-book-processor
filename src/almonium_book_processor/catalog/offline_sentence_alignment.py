"""Idempotent, pair-specific offline sentence jobs. Never changes edition approval."""

import hashlib
import json

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from almonium_book_processor.catalog.models import (
    ContentBlock,
    Edition,
    EditionArtifact,
    PipelineRun,
    Work,
)
from almonium_book_processor.catalog.parallel_content import inherited_pairs, pair_hash
from almonium_book_processor.processing.sentence_correspondence import VERSION, correspond


def processor_version():
    return f"{VERSION}:{hashlib.sha256(settings.NLP_EMBEDDING_MODEL.encode()).hexdigest()[:12]}"


def _pairs(primary_id, secondary_id):
    editions = Edition.objects.select_related("work").filter(
        work__visibility=Work.Visibility.PUBLIC
    )
    primary, secondary = editions.get(pk=primary_id), editions.get(pk=secondary_id)
    if primary.withdrawal_requested_at or secondary.withdrawal_requested_at:
        raise ValueError("Edition is being withdrawn")
    pairs = inherited_pairs(primary, secondary)
    if not pairs:
        raise ValueError("Choose editions with complete inherited paragraph groups")
    return pairs


def _digest(pairs):
    return hashlib.sha256(json.dumps([pair_hash(p, s) for p, s in pairs]).encode()).hexdigest()


@transaction.atomic
def queue_alignment(primary_id, secondary_id):
    from almonium_book_processor.catalog.tasks import align_edition_sentences

    pairs = _pairs(primary_id, secondary_id)
    digest, version = _digest(pairs), processor_version()
    run, created = PipelineRun.objects.get_or_create(
        idempotency_key=f"{version}:{digest}",
        defaults={
            "edition_id": primary_id,
            "stage": PipelineRun.Stage.ALIGN,
            "processor_version": version,
            "input_hash": digest,
            "summary": {
                "secondary_id": str(secondary_id),
                "model": settings.NLP_EMBEDDING_MODEL,
                "method": VERSION,
                "total_blocks": len(pairs),
            },
        },
    )
    retry = PipelineRun.objects.filter(pk=run.pk, status=PipelineRun.Status.FAILED).update(
        status=PipelineRun.Status.QUEUED, error="", finished_at=None
    )
    if created or retry:

        def dispatch():
            try:
                align_edition_sentences.delay(str(run.id))
            except Exception:
                PipelineRun.objects.filter(pk=run.id, status=PipelineRun.Status.QUEUED).update(
                    status=PipelineRun.Status.FAILED,
                    error="Worker queue unavailable; retry this job.",
                    finished_at=timezone.now(),
                )
                raise ValueError("Worker queue unavailable; retry this job.") from None

        transaction.on_commit(dispatch)
    run.refresh_from_db()
    return run


def run_alignment(run_id):
    claimed = PipelineRun.objects.filter(pk=run_id, status=PipelineRun.Status.QUEUED).update(
        status=PipelineRun.Status.RUNNING, started_at=timezone.now()
    )
    if not claimed:
        return
    run = PipelineRun.objects.get(pk=run_id)
    try:
        if run.processor_version != processor_version():
            raise ValueError("Embedding model changed; queue a new alignment")
        pairs = _pairs(run.edition_id, run.summary["secondary_id"])
        if _digest(pairs) != run.input_hash:
            raise ValueError("Text or sentence boundaries changed; queue a new alignment")
        highlighted = fallback = 0
        for index, (primary, secondary) in enumerate(pairs):
            digest = pair_hash(primary, secondary)
            cached = EditionArtifact.objects.filter(
                edition_id=run.edition_id,
                kind=EditionArtifact.Kind.SENTENCE_ALIGNMENT,
                input_hash=digest,
                processor_version=run.processor_version,
            ).first()
            payload = (
                cached.payload
                if cached
                else {
                    **correspond(primary, secondary),
                    "model": settings.NLP_EMBEDDING_MODEL,
                }
            )
            # Match text-revision lock order: blocks first, then editions.
            with transaction.atomic():
                locked = {
                    b.id: b
                    for b in ContentBlock.objects.select_for_update()
                    .filter(pk__in=[primary.id, secondary.id])
                    .order_by("id")
                }
                editions = list(
                    Edition.objects.select_for_update()
                    .filter(pk__in=[primary.edition_id, secondary.edition_id])
                    .order_by("id")
                )
                if (
                    len(locked) != 2
                    or len(editions) != 2
                    or any(e.withdrawal_requested_at for e in editions)
                ):
                    raise ValueError("Edition removed during alignment")
                if pair_hash(locked[primary.id], locked[secondary.id]) != digest:
                    raise ValueError("Text or sentence boundaries changed during alignment")
                EditionArtifact.objects.update_or_create(
                    edition_id=run.edition_id,
                    kind=EditionArtifact.Kind.SENTENCE_ALIGNMENT,
                    input_hash=digest,
                    processor_version=run.processor_version,
                    defaults={
                        "chapter": primary.chapter,
                        "pipeline_run": run,
                        "payload": payload,
                        "is_current": True,
                    },
                )
            highlighted += sum(
                bool(g["certain"] and g["primary"] and g["secondary"]) for g in payload["groups"]
            )
            fallback += not any(g["certain"] for g in payload["groups"])
            PipelineRun.objects.filter(pk=run.id).update(progress=100 * (index + 1) // len(pairs))
        if _digest(_pairs(run.edition_id, run.summary["secondary_id"])) != run.input_hash:
            raise ValueError("Pair changed before completion; queue a new alignment")
        PipelineRun.objects.filter(pk=run.id).update(
            status=PipelineRun.Status.SUCCEEDED,
            finished_at=timezone.now(),
            summary={
                **run.summary,
                "completed_blocks": len(pairs),
                "highlighted_groups": highlighted,
                "paragraph_fallback_blocks": fallback,
            },
        )
    except Exception as error:
        PipelineRun.objects.filter(pk=run.id).update(
            status=PipelineRun.Status.FAILED, error=str(error)[:1000], finished_at=timezone.now()
        )
        raise
