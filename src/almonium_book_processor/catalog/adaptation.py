"""Bounded, staff-only B2 chapter pilots. Never mutates or publishes an edition."""

import difflib
import hashlib
import json
import re
import uuid

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from almonium_book_processor.ai.adaptation import PROMPT_VERSION, SYSTEM_PROMPT, ChapterAdaptation
from almonium_book_processor.ai.openai_provider import OpenAIBatchProvider, response_output_text
from almonium_book_processor.catalog.ai_translation import (
    TRANSLATION_MODEL_PRICING,
    _estimated_cost,
)
from almonium_book_processor.catalog.models import (
    AIRun,
    Chapter,
    Edition,
    ModelConfiguration,
    PipelineRun,
    PromptTemplate,
    Work,
)

VERSION = "b2-chapter-pilot-v1"
PROMPT_NAME = "literary-b2-adaptation-pilot"
MAX_CHARS = 40000
MAX_BLOCKS = 100


def source_snapshot(chapter, block_ids=None):
    edition = chapter.edition
    if edition.work.visibility != Work.Visibility.PUBLIC:
        raise ValueError("Adaptation pilots currently support public catalogue sources only.")
    if edition.withdrawal_requested_at:
        raise ValueError("This edition is being withdrawn.")
    blocks = [
        {
            "block_id": b.block_id,
            "type": b.block_type,
            "text": b.text,
            "align_group": str(b.align_group) if b.align_group else None,
        }
        for b in chapter.blocks.order_by("sequence")
        if block_ids is None or b.block_id in block_ids
    ]
    if not blocks or not any(b["text"].strip() for b in blocks):
        raise ValueError("The chapter has no text.")
    if len(blocks) > MAX_BLOCKS or sum(len(b["text"]) for b in blocks) > MAX_CHARS:
        raise ValueError("Pilot limit: 100 blocks / 40,000 characters. Choose a smaller chapter.")
    return {
        "chapter_id": str(chapter.id),
        "chapter_title": chapter.title,
        "language": edition.language,
        "work": edition.work.title,
        "author": edition.author,
        "source_sha256": edition.source_sha256,
        "target_level": "B2",
        "blocks": blocks,
    }


def digest(data):
    return hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


@transaction.atomic
def queue_pilot(
    edition_id,
    chapter_id,
    *,
    target_edition_id=None,
    block_ids=None,
    dispatch=True,
    editorial_feedback="",
):
    from almonium_book_processor.catalog.tasks import adapt_chapter_pilot

    if not settings.OPENAI_API_KEY:
        raise ValueError("Configure an OpenAI key to generate a pilot.")
    editorial_feedback = editorial_feedback.strip()
    if len(editorial_feedback) > 4000:
        raise ValueError("Editorial feedback is limited to 4,000 characters.")
    edition = Edition.objects.select_for_update().select_related("work").get(pk=edition_id)
    chapter = Chapter.objects.get(pk=chapter_id, edition=edition)
    source = source_snapshot(chapter, block_ids)
    owner = edition
    if target_edition_id is not None:
        owner = Edition.objects.select_for_update().get(
            pk=target_edition_id,
            source_edition=edition,
            work=edition.work,
            edition_type=Edition.EditionType.ADAPTATION,
        )
        if owner.status == Edition.Status.PUBLISHED or owner.withdrawal_requested_at:
            raise ValueError("Cannot generate into a published or withdrawing edition.")
    model = settings.OPENAI_TRANSLATION_QUALITY_MODEL
    configuration, _ = ModelConfiguration.objects.get_or_create(
        name=f"adaptation-pilot-{digest(model)[:16]}-v1",
        defaults={
            "provider": "openai",
            "model": model,
            "purpose": "level_adaptation",
            "parameters": {
                "reasoning_effort": "medium",
                "pricing_per_million": TRANSLATION_MODEL_PRICING["quality"],
            },
        },
    )
    schema = ChapterAdaptation.model_json_schema()
    prompt, _ = PromptTemplate.objects.get_or_create(
        name=PROMPT_NAME,
        version=PROMPT_VERSION,
        defaults={
            "purpose": "level_adaptation",
            "system_prompt": SYSTEM_PROMPT,
            "user_template": "{source_json}",
            "output_schema": schema,
            "active": True,
        },
    )
    if prompt.system_prompt != SYSTEM_PROMPT or prompt.output_schema != schema:
        # The saved version is what past runs were hashed against; an edit must be a new version.
        raise ValueError(
            f"Prompt v{PROMPT_VERSION} is already saved with different text or schema. "
            "Bump PROMPT_VERSION instead of editing a saved prompt."
        )
    body = {
        "model": configuration.model,
        "instructions": prompt.system_prompt,
        "input": json.dumps(source, ensure_ascii=False),
        "reasoning": {"effort": "medium"},
        "max_output_tokens": 20000,
        "store": False,
        "text": {
            "format": {
                "type": "json_schema",
                "name": "chapter_adaptation",
                "strict": True,
                "schema": prompt.output_schema,
            }
        },
    }
    if editorial_feedback:
        body["instructions"] += (
            "\nEDITORIAL CORRECTIONS FROM THE REVIEWER\n"
            "Apply these corrections without weakening fidelity or the B2 reading target. "
            "Generate from the supplied original, not from a previous adaptation.\n"
            + editorial_feedback
        )
    input_hash = digest({"request": body, "processor": VERSION, "prompt": prompt.version})
    run, created = PipelineRun.objects.get_or_create(
        idempotency_key=f"{owner.id}:adapt-pilot:{input_hash}",
        defaults={
            "edition": owner,
            "stage": PipelineRun.Stage.ADAPT,
            "processor_version": VERSION,
            "input_hash": input_hash,
            "summary": {
                "chapter_id": str(chapter.id),
                "chapter_title": chapter.title,
                "target_level": "B2",
                "source_hash": digest(source),
                "source_edition_id": str(edition.id),
                "block_ids": block_ids,
                "editorial_feedback": editorial_feedback,
            },
        },
    )
    if not created and run.status != PipelineRun.Status.FAILED:
        return run
    previous = run.ai_runs.order_by("-created_at").first()
    reusable = False
    if previous and previous.response_payload.get("raw", {}).get("status") == "completed":
        try:
            validate_result(
                ChapterAdaptation.model_validate_json(
                    response_output_text(previous.response_payload["raw"])
                ),
                source,
            )
            reusable = True
        except ValueError:
            pass
    ai = (
        previous
        if reusable
        else AIRun.objects.create(
            edition=owner,
            pipeline_run=run,
            model_configuration=configuration,
            prompt_template=prompt,
            input_hash=input_hash,
            idempotency_key=f"{run.id}:{uuid.uuid4()}",
            request_payload={"body": body, "source": source, "processor_version": VERSION},
        )
    )
    run.status = PipelineRun.Status.QUEUED
    run.error = ""
    run.finished_at = None
    run.summary = {**run.summary, "ai_run_id": str(ai.id)}
    run.save()
    if dispatch:
        transaction.on_commit(lambda: adapt_chapter_pilot.delay(str(run.id)))
    return run


def validate_result(result, source):
    if [b.block_id for b in result.blocks] != [b["block_id"] for b in source["blocks"]]:
        raise ValueError("Adaptation must preserve all source block IDs and their order.")
    warnings = list(result.review_notes)
    for block, original in zip(result.blocks, source["blocks"], strict=True):
        unchanged = block.text == original["text"]
        if (block.decision == "kept") != unchanged:
            warnings.append(
                f"{block.block_id}: corrected model keep/adapt label from exact text comparison."
            )
        block.decision = "kept" if unchanged else "adapted"
        if original["text"].strip() and not block.text.strip():
            raise ValueError(f"Empty adapted block: {block.block_id}")
        if (
            not original["text"].strip()
            or original["type"] in {"heading", "verse_line", "verse_stanza", "stanza"}
        ) and not unchanged:
            raise ValueError(f"Protected block changed: {block.block_id}")
        if not unchanged and not block.reason.strip():
            warnings.append(
                f"{block.block_id}: model omitted the change reason; inspect this edit."
            )
        if not unchanged and _letters(block.text) == _letters(original["text"]):
            warnings.append(
                f"{block.block_id}: only punctuation, spacing or case changed; gratuitous edit."
            )
        if unchanged:
            block.reason = ""
        ratio = len(block.text) / max(1, len(original["text"]))
        if not unchanged and not 0.65 <= ratio <= 1.5:
            warnings.append(
                f"{block.block_id}: length ratio {ratio:.2f}; check for loss or additions."
            )
    return warnings


def run_pilot(run_id, *, provider=None):
    # Atomic claim prevents duplicate deliveries from launching duplicate paid calls.
    # A worker lost during a request requires operator reconciliation, not blind repayment.
    claimed = PipelineRun.objects.filter(pk=run_id, status=PipelineRun.Status.QUEUED).update(
        status=PipelineRun.Status.RUNNING, started_at=timezone.now(), progress=10
    )
    if not claimed:
        return
    run = PipelineRun.objects.get(pk=run_id)
    ai = AIRun.objects.get(pk=run.summary["ai_run_id"])
    source = ai.request_payload["source"]
    source_edition_id = run.summary.get("source_edition_id", run.edition_id)
    block_ids = run.summary.get("block_ids")
    try:
        chapter = Chapter.objects.select_related("edition__work").get(
            pk=source["chapter_id"], edition_id=source_edition_id
        )
        if digest(source_snapshot(chapter, block_ids)) != run.summary["source_hash"]:
            raise ValueError("Source changed before generation. Queue a new pilot.")
        ai.status = AIRun.Status.SUBMITTED
        ai.started_at = timezone.now()
        ai.save(update_fields=["status", "started_at", "updated_at"])
        response = ai.response_payload.get("raw")
        if response is None:
            response = (provider or OpenAIBatchProvider()).respond(ai.request_payload["body"])
            record_response(ai.id, response)
        ai.refresh_from_db()
        if not ai.edition_id:
            raise ValueError("Source removed during generation.")
        if response.get("status") != "completed":
            raise ValueError(
                "Provider did not complete the chapter; partial output is not accepted."
            )
        result = ChapterAdaptation.model_validate_json(response_output_text(response))
        warnings = validate_result(result, source)
        with transaction.atomic():
            Edition.objects.select_for_update().get(pk=run.edition_id)
            chapter = Chapter.objects.select_related("edition__work").get(
                pk=source["chapter_id"], edition_id=source_edition_id
            )
            if digest(source_snapshot(chapter, block_ids)) != run.summary["source_hash"]:
                raise ValueError(
                    "Source changed during generation. Result retained only in AI history."
                )
            ai = AIRun.objects.select_for_update().get(pk=ai.id)
            ai.response_payload = {
                **ai.response_payload,
                "adaptation": result.model_dump(),
                "warnings": warnings,
            }
            ai.status = AIRun.Status.SUCCEEDED
            ai.error = ""
            ai.finished_at = timezone.now()
            ai.save(
                update_fields=["response_payload", "status", "error", "finished_at", "updated_at"]
            )
            run.status = PipelineRun.Status.SUCCEEDED
            run.progress = 100
            run.finished_at = timezone.now()
            run.summary = {
                **run.summary,
                "kept": sum(b.decision == "kept" for b in result.blocks),
                "blocks": len(result.blocks),
                "review_required": True,
            }
            run.save()
    except Exception as error:
        # Never save stale in-memory payloads here: removal must stay scrubbed.
        AIRun.objects.filter(pk=ai.id).update(
            status=AIRun.Status.FAILED, error=type(error).__name__, finished_at=timezone.now()
        )
        PipelineRun.objects.filter(pk=run_id).update(
            status=PipelineRun.Status.FAILED,
            error=str(error)[:1000] if isinstance(error, ValueError) else type(error).__name__,
            finished_at=timezone.now(),
        )
        raise


def record_response(ai_id, response):
    usage = response.get("usage") or {}
    inputs = usage.get("input_tokens", 0)
    cached = (usage.get("input_tokens_details") or {}).get("cached_tokens", 0)
    outputs = usage.get("output_tokens", 0)
    # Lock the ledger, not the network call. Purge may have scrubbed it in flight.
    with transaction.atomic():
        ai = AIRun.objects.select_for_update().get(pk=ai_id)
        ai.add_attempt_usage(
            input_tokens=inputs,
            cached_input_tokens=cached,
            output_tokens=outputs,
            reasoning_tokens=(usage.get("output_tokens_details") or {}).get("reasoning_tokens", 0),
            estimated_cost_usd=_estimated_cost(
                "quality", inputs, cached, outputs, discounted=False
            ),
        )
        ai.provider_request_id = response.get("id", "")
        ai.response_payload = {"raw": response} if ai.edition_id else {}
        ai.save(
            update_fields=[
                *AIRun.USAGE_FIELDS,
                "provider_request_id",
                "response_payload",
                "updated_at",
            ]
        )


def _letters(text):
    return re.sub(r"[\W_]+", "", text).casefold()


def word_diff(original, adapted):
    """Word-level diff as (source segments, target segments) of {op, text} for the review page."""
    a = re.findall(r"\s+|\S+", original)
    b = re.findall(r"\s+|\S+", adapted)
    source, target = [], []
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if i2 > i1:
            source.append({"op": "equal" if op == "equal" else "delete", "text": "".join(a[i1:i2])})
        if j2 > j1:
            target.append({"op": "equal" if op == "equal" else "insert", "text": "".join(b[j1:j2])})
    return source, target


def pilot_context(run):
    ai = run.ai_runs.order_by("-created_at").first()
    source = ai.request_payload["source"] if ai else {}
    result = ai.response_payload.get("adaptation", {}) if ai else {}
    chapter = (
        Chapter.objects.select_related("edition__work")
        .filter(
            pk=run.summary["chapter_id"],
            edition_id=run.summary.get("source_edition_id", run.edition_id),
        )
        .first()
    )
    try:
        stale = (
            not chapter
            or digest(source_snapshot(chapter, run.summary.get("block_ids")))
            != run.summary["source_hash"]
        )
    except ValueError:
        stale = True
    rows = []
    for original, adapted in zip(source.get("blocks", []), result.get("blocks", []), strict=False):
        source_segments, target_segments = word_diff(original["text"], adapted["text"])
        rows.append(
            {
                "source": original,
                "target": adapted,
                "source_segments": source_segments,
                "target_segments": target_segments,
            }
        )
    return {"run": run, "ai": ai, "stale": stale, "rows": rows}
