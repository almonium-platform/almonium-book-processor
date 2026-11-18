"""Idempotent, pair-specific offline sentence jobs. Never changes edition approval."""

import contextlib
import contextvars
import hashlib
import json
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal

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
from almonium_book_processor.processing import remote_embeddings
from almonium_book_processor.processing.nlp import embedding_runtime
from almonium_book_processor.processing.sentence_correspondence import (
    VERSION,
    correspond,
    pair_texts,
    prefetch,
)


def available_models():
    return list(
        dict.fromkeys(
            [
                settings.NLP_EMBEDDING_MODEL,
                settings.SENTENCE_ALIGNMENT_MODEL,
                "sentence-transformers/LaBSE",
            ]
        )
    )


def processor_version(model=None):
    digest = hashlib.sha256((model or settings.NLP_EMBEDDING_MODEL).encode()).hexdigest()[:12]
    return f"{VERSION}:{digest}"


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
def queue_alignment(primary_id, secondary_id, model=None):
    from almonium_book_processor.catalog.tasks import align_edition_sentences

    model = model or settings.NLP_EMBEDDING_MODEL
    if model not in available_models():
        raise ValueError("Choose a supported offline model")
    pairs = _pairs(primary_id, secondary_id)
    digest, version = _digest(pairs), processor_version(model)
    run, created = PipelineRun.objects.get_or_create(
        idempotency_key=f"{version}:{digest}",
        defaults={
            "edition_id": primary_id,
            "stage": PipelineRun.Stage.ALIGN,
            "processor_version": version,
            "input_hash": digest,
            "summary": {
                "secondary_id": str(secondary_id),
                "model": model,
                "method": VERSION,
                "total_blocks": len(pairs),
            },
        },
    )
    # A correction retires the artifacts of every pair it touches; when the
    # text later returns to a digest that already succeeded, the same run has
    # to serve its cached rows again.
    retired = run.status == PipelineRun.Status.SUCCEEDED and (
        EditionArtifact.objects.filter(
            edition_id=primary_id,
            kind=EditionArtifact.Kind.SENTENCE_ALIGNMENT,
            processor_version=version,
            input_hash__in=[pair_hash(p, s) for p, s in pairs],
            is_current=True,
        ).count()
        < len(pairs)
    )
    retry = PipelineRun.objects.filter(
        pk=run.pk,
        status__in=[PipelineRun.Status.FAILED]
        + ([PipelineRun.Status.SUCCEEDED] if retired else []),
    ).update(status=PipelineRun.Status.QUEUED, error="", finished_at=None, progress=0)
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


class _LookAhead:
    """Embed the next window on one background thread while this one is matched.

    A Modal call for 2,048 texts takes 4-6 s, mostly bringing the vectors back over the
    network, and matching those paragraphs takes about as long: done one after the other
    the aligner waited half its time. The thread runs in a copy of the run's context, so
    text the run marked public (remote_embeddings.public_text) may go to Modal from it,
    and nothing else may.
    """

    def __init__(self):
        self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="alignment-ahead")
        self._pending = None

    def start(self, function, *args):
        self._pending = self._pool.submit(contextvars.copy_context().run, function, *args)

    def wait(self):
        """Block until the window started last is embedded; its error is raised here."""

        pending, self._pending = self._pending, None
        if pending is not None:
            pending.result()

    def close(self):
        self._pool.shutdown(wait=True, cancel_futures=True)


def run_alignment(run_id):
    claimed = PipelineRun.objects.filter(pk=run_id, status=PipelineRun.Status.QUEUED).update(
        status=PipelineRun.Status.RUNNING, started_at=timezone.now(), updated_at=timezone.now()
    )
    if not claimed:
        return
    run = PipelineRun.objects.get(pk=run_id)
    remote = contextlib.ExitStack()
    spent_before = remote_embeddings.usage()
    runtime = {}
    try:
        model = run.summary["model"]
        if model not in available_models() or run.processor_version != processor_version(model):
            raise ValueError("Embedding model changed; queue a new alignment")
        pairs = _pairs(run.edition_id, run.summary["secondary_id"])
        if _digest(pairs) != run.input_hash:
            raise ValueError("Text or sentence boundaries changed; queue a new alignment")
        highlighted = fallback = 0
        fallback_reasons = Counter()
        uncertain_groups = unmatched_sentences = 0
        digests = [pair_hash(p, s) for p, s in pairs]
        done = set(
            EditionArtifact.objects.filter(
                edition_id=run.edition_id,
                kind=EditionArtifact.Kind.SENTENCE_ALIGNMENT,
                processor_version=run.processor_version,
                input_hash__in=digests,
            ).values_list("input_hash", flat=True)
        )
        if _on_modal(pairs, digests, done, model):
            # Public works only (_pairs), inside this month's free Modal credits.
            remote.enter_context(remote_embeddings.public_text())
        runtime = embedding_runtime().as_record()

        def window_from(start):
            """The next stretch of pairs whose unaligned texts fill one large call."""

            texts, end = [], start
            while end < len(pairs) and len(texts) < settings.NLP_EMBEDDING_PREFETCH_TEXTS:
                if digests[end] not in done:
                    texts += pair_texts(*pairs[end])
                end += 1
            return end, texts

        # Embed in large calls, not one small call per paragraph pair, and fetch the next
        # call's vectors while this stretch is matched. Closed before the Modal context.
        ahead = _LookAhead()
        remote.callback(ahead.close)
        window_end, (next_end, next_texts) = 0, window_from(0)
        ahead.start(prefetch, next_texts, model)
        for index, (primary, secondary) in enumerate(pairs):
            digest = digests[index]
            if index >= window_end:
                ahead.wait()  # this stretch's vectors are in
                window_end = next_end
                if window_end < len(pairs):
                    next_end, next_texts = window_from(window_end)
                    ahead.start(prefetch, next_texts, model)
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
                    **correspond(primary, secondary, model_name=model),
                    "model": model,
                    "embedding": runtime,
                }
            )
            for side, block in (("primary", primary), ("secondary", secondary)):
                indexes = sorted(index for group in payload["groups"] for index in group[side])
                spans = payload.get(f"{side}_spans") or block.sentences
                if indexes != list(range(len(spans))) or any(
                    not group["primary"] or not group["secondary"] for group in payload["groups"]
                ):
                    raise ValueError("Sentence correspondence does not cover both sides")
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
            paragraph_only = not any(g["certain"] for g in payload["groups"])
            fallback += paragraph_only
            if paragraph_only:
                fallback_reasons[payload.get("fallback_reason", "low_confidence")] += 1
            uncertain_groups += sum(
                not g["certain"] and bool(g["primary"] and g["secondary"])
                for g in payload["groups"]
            )
            unmatched_sentences += sum(
                len(g["primary"]) + len(g["secondary"])
                for g in payload["groups"]
                if not g["primary"] or not g["secondary"]
            )
            # Touch the row: the janitor reads silence as a dead worker.
            PipelineRun.objects.filter(pk=run.id).update(
                progress=100 * (index + 1) // len(pairs), updated_at=timezone.now()
            )
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
                "fallback_reasons": dict(fallback_reasons),
                "uncertain_groups": uncertain_groups,
                "unmatched_sentences": unmatched_sentences,
                "embedding": _embedding_record(runtime, spent_before),
            },
        )
    except Exception as error:
        failed = {"status": PipelineRun.Status.FAILED, "error": str(error)[:1000]}
        if remote_embeddings.usage().since(spent_before).calls:
            # What a failed run bought on Modal stays on the record for the spend guard.
            failed["summary"] = {
                **run.summary,
                "embedding": _embedding_record(runtime, spent_before),
            }
        PipelineRun.objects.filter(pk=run.id).update(**failed, finished_at=timezone.now())
        raise
    finally:
        remote.close()


def _on_modal(pairs, digests, done, model):
    """Whether this run embeds on Modal: the backend says so and the month's budget has room."""

    from almonium_book_processor.catalog import estimates

    chars = sum(
        len(primary.text) + len(secondary.text)
        for (primary, secondary), digest in zip(pairs, digests, strict=True)
        if digest not in done
    )
    return chars > 0 and estimates.offline_alignment(chars, model) is not None


def _embedding_record(runtime, spent_before):
    """Where the run embedded and, on Modal, what it bought there.

    Calls are priced at the card that ran them; the container's start and idle minute,
    whose card is not reported, at the dearest the app may be scheduled on.
    """

    spent = remote_embeddings.usage().since(spent_before)
    if not spent.calls:
        return runtime
    usd = spent.usd + remote_embeddings.cost_usd(0, containers=1)
    return {
        **runtime,
        "modal_calls": spent.calls,
        "modal_texts": spent.texts,
        "gpu_seconds": round(spent.seconds, 2),
        "gpus": spent.seconds_by_gpu,
        "usd": str(usd.quantize(Decimal("0.0001"))),
    }
