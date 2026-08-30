"""Generate a parallel edition by translating a canonical edition block for block.

This is the alignment backbone. Because the model echoes each stable block id,
every generated block inherits the canonical ``align_group`` of its source, so a
parallel edition is aligned by construction: no embedding pass, no adjudication,
and no review queue. Inferred alignment (``ai_alignment``) remains available for
the exceptional case of two independently imported texts.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from typing import Any

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from almonium_book_processor.ai.openai_provider import OpenAIBatchProvider
from almonium_book_processor.ai.translation import (
    TRANSLATION_OUTPUT_SCHEMA,
    TRANSLATION_SYSTEM_PROMPT,
    TRANSLATION_USER_TEMPLATE,
    ChapterTranslation,
    render_source_block,
)
from almonium_book_processor.catalog.models import (
    AIRun,
    Chapter,
    ContentBlock,
    Edition,
    ModelConfiguration,
    PromptTemplate,
    QAWarning,
)
from almonium_book_processor.languages import LANGUAGES

PROMPT_NAME = "literary-block-translation"
PROMPT_VERSION = 1

LOW_CONFIDENCE_WARNING = "translation_low_confidence"
LENGTH_RATIO_WARNING = "translation_length_ratio"
STRUCTURE_WARNING = "translation_structure"

BLOCK_CONFIDENCE_FLOOR = 0.70
CHAPTER_LENGTH_MIN_RATIO = 0.60
CHAPTER_LENGTH_MAX_RATIO = 1.60

# Tiers deliberately exclude gpt-5.6-sol: on a blind chapter comparison it chose
# anachronistic register ("bougie" for a period candle), repeated an adverb the
# source did not repeat, and emitted more output tokens than either alternative.
TRANSLATION_MODEL_PRICING = {
    "draft": {"input": "0.20", "cached_input": "0.02", "output": "1.20"},
    "quality": {"input": "2.00", "cached_input": "0.20", "output": "12.00"},
}

LANGUAGE_NAMES = {language.code: language.name for language in LANGUAGES}

REGISTER_CHOICES = (
    ("contemporary neutral", "Contemporary neutral"),
    ("period-faithful", "Period-faithful"),
    ("lightly modernised", "Lightly modernised"),
)


def language_name(code: str) -> str:
    return LANGUAGE_NAMES.get(code, code)


def _configuration(tier: str) -> tuple[ModelConfiguration, PromptTemplate]:
    if tier not in TRANSLATION_MODEL_PRICING:
        raise ValueError(f"Unknown translation tier: {tier}")
    model = (
        settings.OPENAI_TRANSLATION_DRAFT_MODEL
        if tier == "draft"
        else settings.OPENAI_TRANSLATION_QUALITY_MODEL
    )
    configuration, _ = ModelConfiguration.objects.get_or_create(
        name=f"openai-translation-{tier}-v1",
        defaults={
            "provider": "openai",
            "model": model,
            "purpose": "literary_translation",
            "parameters": {
                "reasoning_effort": "medium",
                "batch_discount": 0.5,
                "pricing_per_million": TRANSLATION_MODEL_PRICING[tier],
            },
        },
    )
    if configuration.model != model:
        configuration.model = model
        configuration.save(update_fields=["model", "updated_at"])
    prompt, _ = PromptTemplate.objects.get_or_create(
        name=PROMPT_NAME,
        version=PROMPT_VERSION,
        defaults={
            "purpose": "literary_translation",
            "system_prompt": TRANSLATION_SYSTEM_PROMPT,
            "user_template": TRANSLATION_USER_TEMPLATE,
            "output_schema": TRANSLATION_OUTPUT_SCHEMA,
            "active": True,
        },
    )
    return configuration, prompt


def _unique_slug(base: str) -> str:
    slug = base
    suffix = 2
    while Edition.objects.filter(slug=slug).exists():
        slug = f"{base}-{suffix}"
        suffix += 1
    return slug


@transaction.atomic
def create_parallel_translation(
    *,
    source_edition: Edition,
    target_language: str,
    register: str,
    tier: str,
) -> Edition:
    """Create the empty parallel edition that a translation batch will fill."""

    if not source_edition.is_canonical:
        raise ValueError("Only a canonical edition can seed a parallel translation")
    if target_language == source_edition.language:
        raise ValueError("The target language must differ from the source language")
    if not source_edition.blocks.exists():
        raise ValueError("The canonical edition has no normalized blocks yet")
    if tier not in TRANSLATION_MODEL_PRICING:
        raise ValueError(f"Unknown translation tier: {tier}")
    if register not in {value for value, _ in REGISTER_CHOICES}:
        raise ValueError(f"Unknown register: {register}")

    work = source_edition.work
    edition = Edition.objects.create(
        slug=_unique_slug(f"{work.slug}-{target_language}-parallel"),
        work=work,
        source_edition=source_edition,
        title=source_edition.work.title,
        author=source_edition.author,
        language=target_language,
        edition_type=Edition.EditionType.MACHINE_TRANSLATION,
        parallel_role=Edition.ParallelRole.PARALLEL,
        translator=f"AI ({register})",
        status=Edition.Status.PROCESSING,
    )
    return edition


def _response_request(
    model: str, system_prompt: str, user_prompt: str, custom_id: str
) -> dict[str, Any]:
    return {
        "custom_id": custom_id,
        "method": "POST",
        "url": "/v1/responses",
        "body": {
            "model": model,
            "instructions": system_prompt,
            "input": user_prompt,
            "reasoning": {"effort": "medium"},
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "chapter_translation",
                    "strict": True,
                    "schema": TRANSLATION_OUTPUT_SCHEMA,
                }
            },
            "store": False,
        },
    }


def _register_of(edition: Edition) -> str:
    translator = edition.translator or ""
    if translator.startswith("AI (") and translator.endswith(")"):
        return translator[4:-1]
    return "contemporary neutral"


def _prepare_translation_run(
    edition_id: str, *, tier: str
) -> AIRun | tuple[AIRun, list[dict[str, Any]]]:
    """Build one request per source chapter and the AIRun that records them.

    Returns a finished AIRun when an identical run already succeeded or is in
    flight, otherwise the run plus the requests to execute.
    """

    edition = Edition.objects.select_related("source_edition", "work").get(id=edition_id)
    source = edition.source_edition
    if source is None:
        raise ValueError("A parallel edition requires a canonical source edition")
    if edition.parallel_role != Edition.ParallelRole.PARALLEL:
        raise ValueError("Only a parallel edition can be filled by translation")

    chapters = list(source.chapters.order_by("sequence"))
    blocks_by_chapter: dict[uuid.UUID, list[ContentBlock]] = {}
    for chapter in chapters:
        rows = list(chapter.blocks.exclude(text="").order_by("sequence"))
        if rows:
            blocks_by_chapter[chapter.id] = rows
    if not blocks_by_chapter:
        raise ValueError("The canonical edition has no translatable blocks")

    configuration, prompt_template = _configuration(tier)
    register = _register_of(edition)
    digest_payload = {
        "source_sha256": source.source_sha256,
        "model": configuration.model,
        "prompt_version": prompt_template.version,
        "register": register,
        "target_language": edition.language,
        "blocks": [
            [block.block_id, block.updated_at.isoformat()]
            for rows in blocks_by_chapter.values()
            for block in rows
        ],
    }
    input_hash = hashlib.sha256(json.dumps(digest_payload, sort_keys=True).encode()).hexdigest()
    idempotency_key = f"{edition.id}:{input_hash}:openai-translate:{tier}:v{PROMPT_VERSION}"
    ai_run, created = AIRun.objects.get_or_create(
        idempotency_key=idempotency_key,
        defaults={
            "edition": edition,
            "model_configuration": configuration,
            "prompt_template": prompt_template,
            "input_hash": input_hash,
        },
    )
    if not created and ai_run.status == AIRun.Status.SUCCEEDED:
        return ai_run
    # Only a Batch run has work in flight at the provider worth protecting. A
    # direct run left "submitted" by a crashed worker must stay restartable.
    if (
        not created
        and ai_run.status == AIRun.Status.SUBMITTED
        and (ai_run.request_payload or {}).get("execution") != "direct"
    ):
        return ai_run

    year = source.work.publication_year
    system_prompt = prompt_template.system_prompt.format(
        source_language_name=language_name(source.language),
        target_language_name=language_name(edition.language),
        work_title=source.work.title,
        author=source.author,
        year_clause=f", published {year}" if year else "",
        register=register,
    )

    requests = []
    manifest = {}
    for chapter in chapters:
        rows = blocks_by_chapter.get(chapter.id)
        if not rows:
            continue
        custom_id = f"chapter-{chapter.sequence}"
        user_prompt = prompt_template.user_template.format(
            chapter_sequence=chapter.sequence,
            chapter_title_clause=f" · {chapter.title}" if chapter.title else "",
            source_language=source.language,
            target_language=edition.language,
            source_blocks="\n".join(render_source_block(block) for block in rows),
        )
        requests.append(
            _response_request(configuration.model, system_prompt, user_prompt, custom_id)
        )
        manifest[custom_id] = {
            "source_chapter_id": str(chapter.id),
            "chapter_sequence": chapter.sequence,
            "chapter_title": chapter.title,
            "block_ids": [block.block_id for block in rows],
            "source_chars": sum(len(block.text) for block in rows),
        }

    ai_run.status = AIRun.Status.QUEUED
    ai_run.started_at = timezone.now()
    ai_run.error = ""
    ai_run.request_payload = {
        "tier": tier,
        "register": register,
        "request_count": len(requests),
        "manifest": manifest,
    }
    ai_run.save(update_fields=["status", "started_at", "error", "request_payload", "updated_at"])
    return ai_run, requests


def submit_translation_batch(edition_id: str, *, tier: str = "quality") -> AIRun:
    """Submit the translation through the Batch API (cheapest, up to 24 hours)."""

    prepared = _prepare_translation_run(edition_id, tier=tier)
    if isinstance(prepared, AIRun):
        return prepared
    ai_run, requests = prepared
    edition = ai_run.edition
    try:
        batch = OpenAIBatchProvider().submit(
            requests,
            metadata={
                "edition_id": str(edition.id),
                "ai_run_id": str(ai_run.id),
                "purpose": "translation",
            },
        )
    except Exception as error:
        ai_run.status = AIRun.Status.FAILED
        ai_run.error = str(error)[:10000]
        ai_run.finished_at = timezone.now()
        ai_run.save(update_fields=["status", "error", "finished_at", "updated_at"])
        raise
    ai_run.status = AIRun.Status.SUBMITTED
    ai_run.provider_request_id = batch.id
    ai_run.request_payload = {**ai_run.request_payload, "execution": "batch"}
    ai_run.response_payload = {"batch_status": batch.status, "input_file_id": batch.input_file_id}
    ai_run.save(
        update_fields=[
            "status",
            "provider_request_id",
            "request_payload",
            "response_payload",
            "updated_at",
        ]
    )
    return ai_run


def _output_text(body: dict[str, Any]) -> str:
    for item in body.get("output", []):
        if item.get("type") != "message":
            continue
        for content in item.get("content", []):
            if content.get("type") == "output_text":
                return content["text"]
    raise ValueError("OpenAI response contained no output text")


def _validate_chapter(translation: ChapterTranslation, chapter_manifest: dict[str, Any]) -> None:
    expected = chapter_manifest["block_ids"]
    returned = [block.block_id for block in translation.blocks]
    if returned != expected:
        missing = sorted(set(expected) - set(returned))
        extra = sorted(set(returned) - set(expected))
        if missing or extra:
            raise ValueError(
                f"Translated blocks do not match the source: missing={missing} extra={extra}"
            )
        raise ValueError("Translated blocks must preserve the source block order")
    empty = [block.block_id for block in translation.blocks if not block.text.strip()]
    if empty:
        raise ValueError(f"Translated blocks must not be empty: {empty}")


def _estimated_cost(
    tier: str,
    input_tokens: int,
    cached_input_tokens: int,
    output_tokens: int,
    *,
    discounted: bool,
) -> Decimal:
    pricing = TRANSLATION_MODEL_PRICING[tier]
    uncached = max(0, input_tokens - cached_input_tokens)
    standard = (
        Decimal(uncached) * Decimal(pricing["input"])
        + Decimal(cached_input_tokens) * Decimal(pricing["cached_input"])
        + Decimal(output_tokens) * Decimal(pricing["output"])
    ) / Decimal(1_000_000)
    return standard * Decimal("0.5") if discounted else standard


def _materialize_chapter(
    edition: Edition,
    translation: ChapterTranslation,
    chapter_manifest: dict[str, Any],
    *,
    model: str,
) -> dict[str, Any]:
    """Persist one translated chapter, inheriting canonical block groups."""

    source_blocks = {
        block.block_id: block
        for block in ContentBlock.objects.filter(
            edition=edition.source_edition,
            block_id__in=chapter_manifest["block_ids"],
        )
    }
    translated_chars = sum(len(block.text) for block in translation.blocks)
    source_chars = chapter_manifest["source_chars"] or 1
    ratio = translated_chars / source_chars

    heading = next(
        (
            block
            for block in translation.blocks
            if source_blocks[block.block_id].block_type == ContentBlock.BlockType.HEADING
        ),
        None,
    )
    chapter = Chapter.objects.create(
        edition=edition,
        sequence=chapter_manifest["chapter_sequence"],
        title=(heading.text if heading else chapter_manifest["chapter_title"])[:500],
    )
    rows = []
    for translated in translation.blocks:
        source_block = source_blocks[translated.block_id]
        rows.append(
            ContentBlock(
                edition=edition,
                chapter=chapter,
                block_id=source_block.block_id,
                sequence=source_block.sequence,
                block_type=source_block.block_type,
                text=translated.text,
                # The canonical group is the whole point: a parallel edition is
                # aligned by construction, not by inference.
                align_group=source_block.align_group,
                source_ref=f"{edition.source_edition.slug}:{source_block.block_id}",
                attributes={
                    "translation": {
                        "model": model,
                        "confidence": translated.confidence,
                        "sentence_count_changed": translated.sentence_count_changed,
                        **({"note": translated.note} if translated.note.strip() else {}),
                    }
                },
            )
        )
    ContentBlock.objects.bulk_create(rows, batch_size=1000)
    return {
        "chapter_sequence": chapter_manifest["chapter_sequence"],
        "length_ratio": round(ratio, 3),
        "low_confidence_block_ids": [
            block.block_id
            for block in translation.blocks
            if block.confidence < BLOCK_CONFIDENCE_FLOOR
        ],
        "sentence_count_changed": sum(
            1 for block in translation.blocks if block.sentence_count_changed
        ),
        "translated_chars": translated_chars,
        "word_count": sum(len(block.text.split()) for block in translation.blocks),
    }


def _record_chapter_warnings(edition: Edition, summary: dict[str, Any]) -> int:
    """Emit reviewable QA for one translated chapter; return actionable count."""

    actionable = 0
    sequence = summary["chapter_sequence"]
    ratio = summary["length_ratio"]
    if not CHAPTER_LENGTH_MIN_RATIO <= ratio <= CHAPTER_LENGTH_MAX_RATIO:
        QAWarning.objects.update_or_create(
            edition=edition,
            code=LENGTH_RATIO_WARNING,
            source_ref=f"chapter:{sequence}",
            resolved_at=None,
            defaults={
                "severity": QAWarning.Severity.WARNING,
                "message": (
                    f"Chapter {sequence} translated to {ratio:.0%} of the source length, "
                    f"outside the {CHAPTER_LENGTH_MIN_RATIO:.0%}-{CHAPTER_LENGTH_MAX_RATIO:.0%} "
                    "band. Check for truncation or runaway generation."
                ),
            },
        )
        actionable += 1
    low_confidence = summary["low_confidence_block_ids"]
    if low_confidence:
        QAWarning.objects.update_or_create(
            edition=edition,
            code=LOW_CONFIDENCE_WARNING,
            source_ref=f"chapter:{sequence}",
            resolved_at=None,
            defaults={
                "severity": QAWarning.Severity.WARNING,
                "message": (
                    f"Chapter {sequence} has {len(low_confidence)} block(s) the translator "
                    f"reported below {BLOCK_CONFIDENCE_FLOOR:.0%} confidence: "
                    f"{', '.join(low_confidence[:10])}"
                ),
            },
        )
        actionable += 1
    if summary["sentence_count_changed"]:
        QAWarning.objects.update_or_create(
            edition=edition,
            code=LOW_CONFIDENCE_WARNING,
            source_ref=f"chapter:{sequence}:sentences",
            resolved_at=None,
            defaults={
                "severity": QAWarning.Severity.INFO,
                "message": (
                    f"Chapter {sequence}: {summary['sentence_count_changed']} block(s) changed "
                    "sentence count. Sentence-level pairing inside those blocks is approximate."
                ),
            },
        )
    return actionable


def complete_translation_batch(
    ai_run: AIRun, output_lines: list[dict[str, Any]], *, discounted: bool = True
) -> dict[str, Any]:
    with transaction.atomic():
        locked_run = (
            AIRun.objects.select_for_update()
            .select_related("model_configuration")
            .get(id=ai_run.id)
        )
        if locked_run.status == AIRun.Status.SUCCEEDED:
            return locked_run.response_payload.get("summary", {})
        summary, failure = _complete_translation_batch_locked(
            locked_run, output_lines, discounted=discounted
        )
    # Raise only after the transaction committed, so the recorded failure and its
    # token accounting survive; raising inside would roll both back.
    if failure:
        raise ValueError(failure)
    return summary


def _complete_translation_batch_locked(
    ai_run: AIRun, output_lines: list[dict[str, Any]], *, discounted: bool = True
) -> tuple[dict[str, Any], str]:
    manifest = ai_run.request_payload["manifest"]
    tier = ai_run.request_payload["tier"]
    model = ai_run.model_configuration.model
    edition = Edition.objects.select_related("source_edition", "work").get(id=ai_run.edition_id)

    validated: dict[str, ChapterTranslation] = {}
    invalid: dict[str, str] = {}
    seen: set[str] = set()
    input_tokens = cached_tokens = output_tokens = reasoning_tokens = 0

    for line in output_lines:
        custom_id = line["custom_id"]
        if custom_id not in manifest:
            raise ValueError(f"Unknown Batch custom_id: {custom_id}")
        if custom_id in seen:
            raise ValueError(f"Duplicate Batch custom_id: {custom_id}")
        seen.add(custom_id)
        response = line.get("response") or {}
        body = response.get("body") or {}
        usage = body.get("usage") or {}
        input_tokens += usage.get("input_tokens", 0)
        output_tokens += usage.get("output_tokens", 0)
        cached_tokens += (usage.get("input_tokens_details") or {}).get("cached_tokens", 0)
        reasoning_tokens += (usage.get("output_tokens_details") or {}).get("reasoning_tokens", 0)
        try:
            if response.get("status_code") != 200:
                raise ValueError(f"Batch request failed with HTTP {response.get('status_code')}")
            translation = ChapterTranslation.model_validate_json(_output_text(body))
            _validate_chapter(translation, manifest[custom_id])
        except ValueError as error:
            invalid[custom_id] = str(error)[:2000]
            continue
        validated[custom_id] = translation

    for custom_id in sorted(set(manifest) - seen):
        invalid[custom_id] = "Batch output omitted this request"

    ai_run.input_tokens = input_tokens
    ai_run.cached_input_tokens = cached_tokens
    ai_run.output_tokens = output_tokens
    ai_run.reasoning_tokens = reasoning_tokens
    ai_run.estimated_cost_usd = _estimated_cost(
        tier, input_tokens, cached_tokens, output_tokens, discounted=discounted
    )
    ai_run.finished_at = timezone.now()

    # A partially translated book is not a book. Refuse to materialize one.
    if invalid:
        ai_run.status = AIRun.Status.FAILED
        ai_run.error = json.dumps(invalid, ensure_ascii=False)[:10000]
        ai_run.response_payload = {**ai_run.response_payload, "invalid_outputs": invalid}
        ai_run.save(
            update_fields=[
                "status",
                "error",
                "input_tokens",
                "cached_input_tokens",
                "output_tokens",
                "reasoning_tokens",
                "estimated_cost_usd",
                "response_payload",
                "finished_at",
                "updated_at",
            ]
        )
        Edition.objects.filter(id=edition.id).update(
            status=Edition.Status.FAILED, updated_at=timezone.now()
        )
        return {}, f"{len(invalid)} chapter translation(s) were unusable"

    chapter_summaries = []
    with transaction.atomic():
        edition.chapters.all().delete()
        edition.warnings.filter(
            code__in=[LOW_CONFIDENCE_WARNING, LENGTH_RATIO_WARNING, STRUCTURE_WARNING]
        ).delete()
        for custom_id in sorted(validated, key=lambda key: manifest[key]["chapter_sequence"]):
            chapter_summaries.append(
                _materialize_chapter(
                    edition, validated[custom_id], manifest[custom_id], model=model
                )
            )
        actionable = sum(_record_chapter_warnings(edition, item) for item in chapter_summaries)
        edition.word_count = sum(item["word_count"] for item in chapter_summaries)
        edition.status = Edition.Status.REVIEW if actionable else Edition.Status.READY
        edition.save(update_fields=["word_count", "status", "updated_at"])

    summary = {
        "chapters": len(chapter_summaries),
        "blocks": sum(len(item["low_confidence_block_ids"]) for item in chapter_summaries),
        "actionable_warnings": actionable,
        "word_count": edition.word_count,
        "chapter_summaries": chapter_summaries,
    }
    ai_run.status = AIRun.Status.SUCCEEDED
    ai_run.response_payload = {
        **ai_run.response_payload,
        "batch_status": "completed",
        "summary": summary,
    }
    ai_run.save(
        update_fields=[
            "status",
            "input_tokens",
            "cached_input_tokens",
            "output_tokens",
            "reasoning_tokens",
            "estimated_cost_usd",
            "response_payload",
            "finished_at",
            "updated_at",
        ]
    )
    return summary, ""


def last_translation_tier(edition: Edition) -> str:
    """Recover the tier a previous translation attempt used, for retries."""

    run = (
        AIRun.objects.filter(
            edition=edition,
            prompt_template__name=PROMPT_NAME,
        )
        .order_by("-created_at")
        .first()
    )
    tier = (run.request_payload or {}).get("tier") if run else None
    return tier if tier in TRANSLATION_MODEL_PRICING else "quality"


def last_translation_mode(edition: Edition) -> str:
    """Recover how a previous attempt was executed, for retries."""

    run = (
        AIRun.objects.filter(edition=edition, prompt_template__name=PROMPT_NAME)
        .order_by("-created_at")
        .first()
    )
    execution = (run.request_payload or {}).get("execution") if run else None
    return "batch" if execution == "batch" else "direct"


DIRECT_TRANSLATION_WORKERS = 4


def _direct_output_line(provider: OpenAIBatchProvider, request: dict[str, Any]) -> dict[str, Any]:
    """Execute one Batch-shaped request directly, in Batch output-line shape."""

    try:
        body = provider.respond(request["body"])
    except Exception as error:  # recorded per chapter; the run fails as a whole
        return {
            "custom_id": request["custom_id"],
            "response": {"status_code": 502, "body": {"error": str(error)[:500]}},
        }
    return {"custom_id": request["custom_id"], "response": {"status_code": 200, "body": body}}


def run_translation_inline(edition_id: str, *, tier: str = "quality") -> AIRun:
    """Translate without the Batch API, using direct Responses calls.

    Same requests, same validation, same QA gates. It forfeits the 50% Batch
    discount but finishes in minutes and does not depend on the Batch service.
    """

    prepared = _prepare_translation_run(edition_id, tier=tier)
    if isinstance(prepared, AIRun):
        return prepared
    ai_run, requests = prepared

    ai_run.status = AIRun.Status.SUBMITTED
    ai_run.provider_request_id = f"direct:{ai_run.id}"
    ai_run.request_payload = {**ai_run.request_payload, "execution": "direct"}
    ai_run.response_payload = {"batch_status": "direct"}
    ai_run.save(
        update_fields=[
            "status",
            "provider_request_id",
            "request_payload",
            "response_payload",
            "updated_at",
        ]
    )

    provider = OpenAIBatchProvider()
    # Threads only make HTTP calls; every database write happens on this thread.
    with ThreadPoolExecutor(max_workers=DIRECT_TRANSLATION_WORKERS) as pool:
        output_lines = list(
            pool.map(lambda request: _direct_output_line(provider, request), requests)
        )
    complete_translation_batch(ai_run, output_lines, discounted=False)
    return ai_run
