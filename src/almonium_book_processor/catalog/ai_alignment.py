from __future__ import annotations

import hashlib
import json
import uuid
from collections import defaultdict
from decimal import Decimal
from typing import Any

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from almonium_book_processor.ai.alignment import (
    ALIGNMENT_OUTPUT_SCHEMA,
    ALIGNMENT_SYSTEM_PROMPT,
    ALIGNMENT_USER_TEMPLATE,
    ChapterAdjudication,
    render_block,
)
from almonium_book_processor.ai.openai_provider import OpenAIBatchProvider
from almonium_book_processor.catalog.models import (
    AIRun,
    AlignmentGroupReview,
    BlockAlignment,
    ChapterAlignment,
    Edition,
    ModelConfiguration,
    PromptTemplate,
    QAWarning,
)

PROMPT_NAME = "literary-block-alignment"
PROMPT_VERSION = 1
AI_WARNING_CODE = "alignment_ai_uncertain"

MODEL_PRICING = {
    "primary": {"input": "0.20", "cached_input": "0.02", "output": "1.20"},
    "escalation": {"input": "2.00", "cached_input": "0.20", "output": "12.00"},
}


def _configuration(tier: str) -> tuple[ModelConfiguration, PromptTemplate]:
    if tier not in MODEL_PRICING:
        raise ValueError(f"Unknown AI alignment tier: {tier}")
    model = (
        settings.OPENAI_ALIGNMENT_PRIMARY_MODEL
        if tier == "primary"
        else settings.OPENAI_ALIGNMENT_ESCALATION_MODEL
    )
    configuration, _ = ModelConfiguration.objects.get_or_create(
        name=f"openai-alignment-{tier}-v1",
        defaults={
            "provider": "openai",
            "model": model,
            "purpose": "alignment_adjudication",
            "parameters": {
                "reasoning_effort": "medium",
                "batch_discount": 0.5,
                "pricing_per_million": MODEL_PRICING[tier],
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
            "purpose": "alignment_adjudication",
            "system_prompt": ALIGNMENT_SYSTEM_PROMPT,
            "user_template": ALIGNMENT_USER_TEMPLATE,
            "output_schema": ALIGNMENT_OUTPUT_SCHEMA,
            "active": True,
        },
    )
    return configuration, prompt


def _chapter_groups(edition: Edition, group_ids: list[str] | None = None) -> list[dict[str, Any]]:
    mappings = ChapterAlignment.objects.filter(target_edition=edition).select_related(
        "source_chapter", "target_chapter"
    )
    if group_ids:
        mappings = mappings.filter(group_id__in=group_ids)
    grouped: dict[uuid.UUID, list[ChapterAlignment]] = defaultdict(list)
    for mapping in mappings.order_by("target_chapter__sequence", "source_chapter__sequence"):
        grouped[mapping.group_id].append(mapping)

    groups = []
    for group_id, rows in grouped.items():
        source_chapter_ids = {row.source_chapter_id for row in rows}
        target_chapter_ids = {row.target_chapter_id for row in rows}
        source_blocks = list(
            edition.source_edition.blocks.filter(chapter_id__in=source_chapter_ids)
            .exclude(text="")
            .select_related("chapter")
            .order_by("chapter__sequence", "sequence")
        )
        target_blocks = list(
            edition.blocks.filter(chapter_id__in=target_chapter_ids)
            .exclude(text="")
            .select_related("chapter")
            .order_by("chapter__sequence", "sequence")
        )
        local_alignments = BlockAlignment.objects.filter(
            target_edition=edition,
            source_block__chapter_id__in=source_chapter_ids,
            target_block__chapter_id__in=target_chapter_ids,
        ).select_related("source_block", "target_block")
        groups.append(
            {
                "group_id": group_id,
                "source_chapters": sorted({row.source_chapter.sequence for row in rows}),
                "target_chapters": sorted({row.target_chapter.sequence for row in rows}),
                "source_blocks": source_blocks,
                "target_blocks": target_blocks,
                "local_candidates": [
                    {
                        "source_block_id": str(item.source_block_id),
                        "target_block_id": str(item.target_block_id),
                        "confidence": item.confidence,
                    }
                    for item in local_alignments
                ],
            }
        )
    return groups


def _response_request(model: str, prompt: str, custom_id: str) -> dict[str, Any]:
    return {
        "custom_id": custom_id,
        "method": "POST",
        "url": "/v1/responses",
        "body": {
            "model": model,
            "instructions": ALIGNMENT_SYSTEM_PROMPT,
            "input": prompt,
            "reasoning": {"effort": "medium"},
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "chapter_adjudication",
                    "strict": True,
                    "schema": ALIGNMENT_OUTPUT_SCHEMA,
                }
            },
            "store": False,
        },
    }


def submit_alignment_batch(
    edition_id: str,
    *,
    tier: str = "primary",
    group_ids: list[str] | None = None,
) -> AIRun:
    edition = Edition.objects.select_related("source_edition").get(id=edition_id)
    if edition.source_edition is None:
        raise ValueError("A source edition is required for AI alignment")
    groups = _chapter_groups(edition, group_ids)
    if not groups:
        raise ValueError("Run local chapter alignment before AI adjudication")
    configuration, prompt_template = _configuration(tier)
    digest_payload = {
        "source_sha256": edition.source_edition.source_sha256,
        "target_sha256": edition.source_sha256,
        "model": configuration.model,
        "prompt_version": prompt_template.version,
        "groups": [str(group["group_id"]) for group in groups],
        "blocks": [
            [str(block.id), block.updated_at.isoformat()]
            for group in groups
            for block in [*group["source_blocks"], *group["target_blocks"]]
        ],
    }
    input_hash = hashlib.sha256(json.dumps(digest_payload, sort_keys=True).encode()).hexdigest()
    idempotency_key = f"{edition.id}:{input_hash}:openai-align:{tier}:v{PROMPT_VERSION}"
    ai_run, created = AIRun.objects.get_or_create(
        idempotency_key=idempotency_key,
        defaults={
            "edition": edition,
            "model_configuration": configuration,
            "prompt_template": prompt_template,
            "input_hash": input_hash,
        },
    )
    if not created and ai_run.status in {AIRun.Status.SUBMITTED, AIRun.Status.SUCCEEDED}:
        return ai_run

    requests = []
    manifest = {}
    for group in groups:
        custom_id = f"chapter-group-{group['group_id']}"
        user_prompt = prompt_template.user_template.format(
            source_language=edition.source_edition.language,
            target_language=edition.language,
            source_chapters=group["source_chapters"],
            target_chapters=group["target_chapters"],
            source_blocks="\n".join(render_block(block) for block in group["source_blocks"]),
            target_blocks="\n".join(render_block(block) for block in group["target_blocks"]),
            local_candidates=json.dumps(group["local_candidates"], ensure_ascii=False),
        )
        requests.append(_response_request(configuration.model, user_prompt, custom_id))
        manifest[custom_id] = {
            "chapter_group_id": str(group["group_id"]),
            "source_chapters": group["source_chapters"],
            "target_chapters": group["target_chapters"],
            "source_block_ids": [str(block.id) for block in group["source_blocks"]],
            "target_block_ids": [str(block.id) for block in group["target_blocks"]],
        }

    ai_run.status = AIRun.Status.QUEUED
    ai_run.started_at = timezone.now()
    ai_run.error = ""
    ai_run.request_payload = {"tier": tier, "request_count": len(requests), "manifest": manifest}
    ai_run.save(update_fields=["status", "started_at", "error", "request_payload", "updated_at"])
    try:
        batch = OpenAIBatchProvider().submit(
            requests,
            metadata={"edition_id": str(edition.id), "ai_run_id": str(ai_run.id), "tier": tier},
        )
    except Exception as error:
        ai_run.status = AIRun.Status.FAILED
        ai_run.error = str(error)[:10000]
        ai_run.finished_at = timezone.now()
        ai_run.save(update_fields=["status", "error", "finished_at", "updated_at"])
        raise
    ai_run.status = AIRun.Status.SUBMITTED
    ai_run.provider_request_id = batch.id
    ai_run.response_payload = {"batch_status": batch.status, "input_file_id": batch.input_file_id}
    ai_run.save(
        update_fields=[
            "status",
            "provider_request_id",
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


def _validate_adjudication(
    adjudication: ChapterAdjudication,
    manifest: dict[str, Any],
) -> None:
    allowed_source = set(manifest["source_block_ids"])
    allowed_target = set(manifest["target_block_ids"])
    returned_source = {
        block_id for item in adjudication.alignments for block_id in item.source_block_ids
    } | set(adjudication.unmatched_source_block_ids)
    returned_target = {
        block_id for item in adjudication.alignments for block_id in item.target_block_ids
    } | set(adjudication.unmatched_target_block_ids)
    if returned_source != allowed_source or returned_target != allowed_target:
        raise ValueError("AI result must account for every supplied block exactly once")
    source_position = {
        block_id: index for index, block_id in enumerate(manifest["source_block_ids"])
    }
    target_position = {
        block_id: index for index, block_id in enumerate(manifest["target_block_ids"])
    }
    positions = [
        (
            min(source_position[block_id] for block_id in item.source_block_ids),
            min(target_position[block_id] for block_id in item.target_block_ids),
        )
        for item in adjudication.alignments
    ]
    if positions != sorted(positions):
        raise ValueError("AI alignment groups must preserve monotonic reading order")


def _apply_adjudication(
    edition: Edition,
    adjudication: ChapterAdjudication,
    manifest: dict[str, Any],
    *,
    model: str,
    tier: str,
) -> bool:
    _validate_adjudication(adjudication, manifest)
    target_ids = manifest["target_block_ids"]
    existing_group_ids = list(
        BlockAlignment.objects.filter(target_edition=edition, target_block_id__in=target_ids)
        .values_list("group_id", flat=True)
        .distinct()
    )
    if AlignmentGroupReview.objects.filter(
        target_edition=edition,
        group_id__in=existing_group_ids,
        reviewer__isnull=False,
    ).exists():
        return False
    uncertain = (
        not adjudication.same_text
        or adjudication.needs_human_review
        or adjudication.confidence < settings.OPENAI_ALIGNMENT_CONFIDENCE
    )
    if uncertain:
        if tier == "escalation":
            QAWarning.objects.update_or_create(
                edition=edition,
                code=AI_WARNING_CODE,
                source_ref=f"chapter-group:{manifest['chapter_group_id']}",
                resolved_at=None,
                defaults={
                    "severity": QAWarning.Severity.WARNING,
                    "message": (
                        f"{model} could not confidently align source chapters "
                        f"{manifest['source_chapters']} with target chapters "
                        f"{manifest['target_chapters']}: {adjudication.notes}"
                    ),
                },
            )
        return True

    source_blocks = {
        str(block.id): block
        for block in edition.source_edition.blocks.filter(id__in=manifest["source_block_ids"])
    }
    target_blocks = {str(block.id): block for block in edition.blocks.filter(id__in=target_ids)}
    with transaction.atomic():
        AlignmentGroupReview.objects.filter(
            target_edition=edition,
            group_id__in=existing_group_ids,
            decision=AlignmentGroupReview.Decision.AI_ACCEPTED,
        ).delete()
        BlockAlignment.objects.filter(
            target_edition=edition,
            target_block_id__in=target_ids,
        ).delete()
        rows = []
        reviews = []
        for decision in adjudication.alignments:
            group_id = uuid.uuid4()
            for source_id in decision.source_block_ids:
                for target_id in decision.target_block_ids:
                    rows.append(
                        BlockAlignment(
                            source_edition=edition.source_edition,
                            target_edition=edition,
                            source_block=source_blocks[source_id],
                            target_block=target_blocks[target_id],
                            group_id=group_id,
                            confidence=decision.confidence,
                            strategy=f"openai-{model}-structured-v1",
                        )
                    )
            reviews.append(
                AlignmentGroupReview(
                    target_edition=edition,
                    group_id=group_id,
                    decision=AlignmentGroupReview.Decision.AI_ACCEPTED,
                    source_block_ids=decision.source_block_ids,
                    target_block_ids=decision.target_block_ids,
                    notes=f"{model}: {decision.evidence}",
                )
            )
        BlockAlignment.objects.bulk_create(rows, batch_size=1000)
        AlignmentGroupReview.objects.bulk_create(reviews, batch_size=500)
        edition.warnings.filter(
            code="alignment_low_confidence",
            block_id__in=target_ids,
            resolved_at=None,
        ).update(resolved_at=timezone.now())
        edition.warnings.filter(
            code=AI_WARNING_CODE,
            source_ref=f"chapter-group:{manifest['chapter_group_id']}",
            resolved_at=None,
        ).update(resolved_at=timezone.now())
    return False


def _estimated_batch_cost(
    tier: str,
    input_tokens: int,
    cached_input_tokens: int,
    output_tokens: int,
) -> Decimal:
    pricing = MODEL_PRICING[tier]
    uncached = max(0, input_tokens - cached_input_tokens)
    standard = (
        Decimal(uncached) * Decimal(pricing["input"])
        + Decimal(cached_input_tokens) * Decimal(pricing["cached_input"])
        + Decimal(output_tokens) * Decimal(pricing["output"])
    ) / Decimal(1_000_000)
    return standard * Decimal("0.5")


def _record_invalid_output_warning(
    edition: Edition,
    manifest: dict[str, Any],
    *,
    model: str,
    error: str,
) -> None:
    QAWarning.objects.update_or_create(
        edition=edition,
        code=AI_WARNING_CODE,
        source_ref=f"chapter-group:{manifest['chapter_group_id']}",
        resolved_at=None,
        defaults={
            "severity": QAWarning.Severity.WARNING,
            "message": (
                f"{model} returned an invalid alignment for source chapters "
                f"{manifest['source_chapters']} and target chapters "
                f"{manifest['target_chapters']}: {error}"
            )[:2000],
        },
    )


def complete_alignment_batch(ai_run: AIRun, output_lines: list[dict[str, Any]]) -> list[str]:
    with transaction.atomic():
        locked_run = (
            AIRun.objects.select_for_update()
            .select_related("model_configuration")
            .get(id=ai_run.id)
        )
        if locked_run.status == AIRun.Status.SUCCEEDED:
            return locked_run.response_payload.get("uncertain_chapter_group_ids", [])
        return _complete_alignment_batch_locked(locked_run, output_lines)


def _complete_alignment_batch_locked(
    ai_run: AIRun, output_lines: list[dict[str, Any]]
) -> list[str]:
    manifest = ai_run.request_payload["manifest"]
    tier = ai_run.request_payload["tier"]
    validated_outputs = {}
    invalid_outputs = {}
    seen_custom_ids = set()
    uncertain_group_ids = []
    input_tokens = cached_tokens = output_tokens = reasoning_tokens = 0
    edition = Edition.objects.select_related("source_edition").get(id=ai_run.edition_id)
    for line in output_lines:
        custom_id = line["custom_id"]
        if custom_id not in manifest:
            raise ValueError(f"Unknown Batch custom_id: {custom_id}")
        if custom_id in seen_custom_ids:
            raise ValueError(f"Duplicate Batch custom_id: {custom_id}")
        seen_custom_ids.add(custom_id)
        group_manifest = manifest[custom_id]
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
            adjudication = ChapterAdjudication.model_validate_json(_output_text(body))
            _validate_adjudication(adjudication, group_manifest)
        except ValueError as error:
            error_text = str(error)
            invalid_outputs[custom_id] = error_text
            uncertain_group_ids.append(group_manifest["chapter_group_id"])
            if tier == "escalation":
                _record_invalid_output_warning(
                    edition,
                    group_manifest,
                    model=ai_run.model_configuration.model,
                    error=error_text,
                )
            continue
        uncertain = _apply_adjudication(
            edition,
            adjudication,
            group_manifest,
            model=ai_run.model_configuration.model,
            tier=tier,
        )
        if uncertain:
            uncertain_group_ids.append(group_manifest["chapter_group_id"])
        validated_outputs[custom_id] = adjudication.model_dump(mode="json")
    for custom_id in sorted(set(manifest) - seen_custom_ids):
        group_manifest = manifest[custom_id]
        error_text = "Batch output omitted this request"
        invalid_outputs[custom_id] = error_text
        uncertain_group_ids.append(group_manifest["chapter_group_id"])
        if tier == "escalation":
            _record_invalid_output_warning(
                edition,
                group_manifest,
                model=ai_run.model_configuration.model,
                error=error_text,
            )
    ai_run.status = AIRun.Status.SUCCEEDED
    ai_run.input_tokens = input_tokens
    ai_run.cached_input_tokens = cached_tokens
    ai_run.output_tokens = output_tokens
    ai_run.reasoning_tokens = reasoning_tokens
    ai_run.estimated_cost_usd = _estimated_batch_cost(
        tier, input_tokens, cached_tokens, output_tokens
    )
    ai_run.response_payload = {
        **ai_run.response_payload,
        "batch_status": "completed",
        "validated_outputs": validated_outputs,
        "invalid_outputs": invalid_outputs,
        "uncertain_chapter_group_ids": uncertain_group_ids,
    }
    ai_run.finished_at = timezone.now()
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
    return uncertain_group_ids
