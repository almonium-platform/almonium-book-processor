"""Translations and library ingests the product API orders, as jobs it can watch.

The product's /ops console decides; this service runs. An order arrives with the
API's own job id, which becomes the edition's ``external_job_id``: the second
identical order returns the first edition instead of paying the provider twice,
and the id rides the publication payload back so the API can settle what it
started. Nothing here is a new pipeline: the entry points are the ones the staff
form already uses, plus a deterministic cost estimate the console shows before
anyone approves.
"""

from __future__ import annotations

import logging
import math
import uuid
from decimal import Decimal
from typing import Any

from django.db import transaction
from django.utils import timezone

from almonium_book_processor.ai.translation import (
    TRANSLATION_SYSTEM_PROMPT,
    TRANSLATION_USER_TEMPLATE,
)
from almonium_book_processor.catalog.ai_translation import (
    PROMPT_NAME,
    TRANSLATION_MODEL_PRICING,
    create_parallel_translation,
)
from almonium_book_processor.catalog.models import AIRun, Edition, Work
from almonium_book_processor.languages import LANGUAGE_CHOICES

logger = logging.getLogger(__name__)

TRANSLATION_TIERS = tuple(TRANSLATION_MODEL_PRICING)
TRANSLATION_MODES = ("batch", "inline")
DEFAULT_REGISTER = Edition.LiteraryRegister.CONTEMPORARY

# Rough token arithmetic, deliberately simple and deterministic: about four
# characters to a token, every chapter re-sends the prompts, the model answers
# in roughly the source's length plus a JSON envelope per block.
CHARS_PER_TOKEN = 4
OUTPUT_TO_INPUT_RATIO = Decimal("1.15")
ENVELOPE_TOKENS_PER_BLOCK = 24
BATCH_DISCOUNT = Decimal("0.5")
COST_PLACES = Decimal("0.000001")

LANGUAGE_CODES = {code for code, _ in LANGUAGE_CHOICES}


class JobNotFound(LookupError):
    pass


class JobConflict(RuntimeError):
    pass


def _tokens(chars: int) -> int:
    return math.ceil(chars / CHARS_PER_TOKEN)


def _price(tier: str, input_tokens: int, output_tokens: int, *, mode: str) -> Decimal:
    pricing = TRANSLATION_MODEL_PRICING[tier]
    cost = (
        Decimal(input_tokens) * Decimal(pricing["input"])
        + Decimal(output_tokens) * Decimal(pricing["output"])
    ) / Decimal(1_000_000)
    if mode == "batch":
        cost *= BATCH_DISCOUNT
    return cost.quantize(COST_PLACES)


def _published_canonical(edition_slug: str) -> Edition:
    edition = (
        Edition.objects.select_related("work")
        .filter(
            slug=edition_slug,
            status=Edition.Status.PUBLISHED,
            work__visibility=Work.Visibility.PUBLIC,
            parallel_role=Edition.ParallelRole.CANONICAL,
        )
        .first()
    )
    if edition is None:
        raise JobNotFound("Published canonical edition not found.")
    return edition


def _check_options(edition: Edition, target_language: str, tier: str, mode: str) -> None:
    if target_language not in LANGUAGE_CODES:
        raise ValueError(f"Unsupported target language: {target_language}")
    if target_language == edition.language:
        raise ValueError("The target language must differ from the source language")
    if tier not in TRANSLATION_TIERS:
        raise ValueError(f"Unknown translation tier: {tier}")
    if mode not in TRANSLATION_MODES:
        raise ValueError(f"Unknown translation mode: {mode}")


def estimate_translation(
    *, edition_slug: str, target_language: str, tier: str = "quality", mode: str = "batch"
) -> dict[str, Any]:
    """What a translation of this edition should cost, before anyone pays for it."""

    edition = _published_canonical(edition_slug)
    _check_options(edition, target_language, tier, mode)

    prompt_tokens = _tokens(len(TRANSLATION_SYSTEM_PROMPT) + len(TRANSLATION_USER_TEMPLATE))
    chapters = blocks = source_chars = 0
    input_tokens = output_tokens = 0
    for chapter in edition.chapters.order_by("sequence"):
        texts = list(chapter.blocks.exclude(text="").values_list("text", flat=True))
        if not texts:
            continue
        chapters += 1
        blocks += len(texts)
        chapter_chars = sum(len(text) for text in texts)
        source_chars += chapter_chars
        text_tokens = _tokens(chapter_chars)
        input_tokens += text_tokens + prompt_tokens
        output_tokens += math.ceil(text_tokens * OUTPUT_TO_INPUT_RATIO)
        output_tokens += ENVELOPE_TOKENS_PER_BLOCK * len(texts)

    return {
        "edition_id": str(edition.id),
        "edition_slug": edition.slug,
        "target_language": target_language,
        "tier": tier,
        "mode": mode,
        "chapters": chapters,
        "blocks": blocks,
        "source_chars": source_chars,
        "estimated_input_tokens": input_tokens,
        "estimated_output_tokens": output_tokens,
        "estimated_cost_usd": str(_price(tier, input_tokens, output_tokens, mode=mode)),
    }


def start_translation_job(
    *,
    job_id: uuid.UUID,
    edition_slug: str,
    target_language: str,
    tier: str = "quality",
    mode: str = "batch",
    register: str = DEFAULT_REGISTER,
    auto_publish: bool = True,
) -> tuple[Edition, bool]:
    """Create and queue the parallel edition for one approved request.

    Returns the edition and whether it was created by this call; a repeated
    ``job_id`` finds the edition it already made.
    """

    existing = Edition.objects.select_related("work", "source_edition").filter(
        external_job_id=job_id
    )
    found = existing.first()
    if found is not None:
        return found, False

    source = _published_canonical(edition_slug)
    _check_options(source, target_language, tier, mode)

    from almonium_book_processor.catalog.tasks import (
        prepare_translation,
        translate_edition_inline,
    )

    with transaction.atomic():
        edition = create_parallel_translation(
            source_edition=source,
            target_language=target_language,
            register=register,
            tier=tier,
        )
        edition.external_job_id = job_id
        edition.auto_publish = auto_publish
        # A machine translation reads at about its source's level; an editor may
        # still change it before publication.
        edition.cefr_level = source.cefr_level
        edition.save(update_fields=["external_job_id", "auto_publish", "cefr_level", "updated_at"])
        if mode == "batch":
            transaction.on_commit(lambda: prepare_translation.delay(str(edition.id), tier=tier))
        else:
            transaction.on_commit(lambda: translate_edition_inline.delay(str(edition.id), tier))
    return edition, True


def _latest_translation_run(edition: Edition) -> AIRun | None:
    return (
        AIRun.objects.filter(edition=edition, prompt_template__name=PROMPT_NAME)
        .order_by("-created_at")
        .first()
    )


def _translation_phase(edition: Edition, run: AIRun | None) -> str:
    if edition.status == Edition.Status.PUBLISHED:
        return "published"
    if edition.status == Edition.Status.FAILED:
        return "failed"
    if edition.status == Edition.Status.REVIEW:
        return "qa_gate"
    if edition.status == Edition.Status.READY:
        return "publishing"
    if run is not None and run.status == AIRun.Status.SUCCEEDED:
        return "aligning"
    return "translating"


def _progress(run: AIRun | None) -> dict[str, int] | None:
    if run is None:
        return None
    counts = (run.response_payload or {}).get("request_counts") or {}
    total = counts.get("total")
    if not total:
        return None
    return {"completed": int(counts.get("completed", 0)), "total": int(total)}


def _edition_cost(edition: Edition) -> str:
    total = Decimal("0")
    for value in AIRun.objects.filter(edition=edition).values_list("estimated_cost_usd", flat=True):
        if value is not None:
            total += value
    return str(total.quantize(COST_PLACES)) if total else "0"


def translation_job(edition_id: uuid.UUID) -> Edition:
    edition = (
        Edition.objects.select_related("source_edition", "work")
        .filter(
            id=edition_id,
            external_job_id__isnull=False,
            edition_type=Edition.EditionType.MACHINE_TRANSLATION,
        )
        .first()
    )
    if edition is None:
        raise JobNotFound("Translation job not found.")
    return edition


def translation_status(edition: Edition) -> dict[str, Any]:
    run = _latest_translation_run(edition)
    return {
        "edition_id": str(edition.id),
        "edition_slug": edition.slug,
        "source_edition_slug": edition.source_edition.slug if edition.source_edition else None,
        "target_language": edition.language,
        "status": edition.status,
        "phase": _translation_phase(edition, run),
        "progress": _progress(run),
        "estimated_cost_usd": _edition_cost(edition),
        "error": (run.error if run else "") or "",
        "started_at": edition.created_at,
        "published_at": edition.published_at,
        "published_book_id": edition.published_book_id,
    }


def cancel_translation(edition: Edition) -> Edition:
    """Stop a translation the console no longer wants; the ledger keeps its cost."""

    if edition.status == Edition.Status.PUBLISHED:
        raise JobConflict("Published editions cannot be cancelled.")
    run = _latest_translation_run(edition)
    now = timezone.now()
    if run is not None and run.status in {AIRun.Status.QUEUED, AIRun.Status.SUBMITTED}:
        execution = (run.request_payload or {}).get("execution")
        if run.provider_request_id and execution == "batch":
            try:
                from almonium_book_processor.ai.openai_provider import OpenAIBatchProvider

                OpenAIBatchProvider().cancel(run.provider_request_id)
            except Exception:
                logger.exception("Could not cancel batch %s at the provider", run.provider_request_id)
        run.status = AIRun.Status.FAILED
        run.error = "Cancelled by operator"
        run.finished_at = now
        run.save(update_fields=["status", "error", "finished_at", "updated_at"])
    edition.status = Edition.Status.FAILED
    edition.auto_publish = False
    edition.save(update_fields=["status", "auto_publish", "updated_at"])
    return edition


def continue_after_translation(edition_id: str) -> bool:
    """Queue what follows a finished translation: enrichment, and publication if ordered.

    Returns whether publication was queued. A parallel edition is aligned by
    construction, so it only needs sentence splitting before it may go out; the
    chain runs that first because publication insists on a current split.
    """

    from almonium_book_processor.catalog.tasks import publish_edition, split_edition_sentences

    edition = Edition.objects.get(id=edition_id)
    if edition.auto_publish and edition.status == Edition.Status.READY:
        (split_edition_sentences.si(edition_id) | publish_edition.si(edition_id)).delay()
        return True
    split_edition_sentences.delay(edition_id)
    return False


# --- Library ingests -------------------------------------------------------


def _ingest_phase(edition: Edition) -> str:
    if edition.status == Edition.Status.PUBLISHED:
        return "published"
    if edition.status == Edition.Status.FAILED:
        return "failed"
    if edition.status == Edition.Status.REVIEW:
        return "review"
    if edition.status == Edition.Status.READY:
        return "ready"
    return "ingesting"


def library_ingest(edition_id: uuid.UUID) -> Edition:
    edition = (
        Edition.objects.select_related("work")
        .filter(
            id=edition_id,
            external_job_id__isnull=False,
            work__visibility=Work.Visibility.PUBLIC,
            source_edition__isnull=True,
        )
        .first()
    )
    if edition is None:
        raise JobNotFound("Library ingest not found.")
    return edition


def library_ingest_status(edition: Edition) -> dict[str, Any]:
    latest_run = edition.pipeline_runs.order_by("-created_at").first()
    return {
        "edition_id": str(edition.id),
        "slug": edition.slug,
        "status": edition.status,
        "phase": _ingest_phase(edition),
        "progress": latest_run.progress if latest_run else 0,
        "error": (latest_run.error if latest_run else "") or "",
        "published_at": edition.published_at,
        "published_book_id": edition.published_book_id,
    }
