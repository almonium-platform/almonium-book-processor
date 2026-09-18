"""Resumable chapter analysis. Every provider attempt has its own spend-ledger row.

Validated window results live in AIRun; deterministic chapter and book
projections are separate versioned artifacts.
"""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from almonium_book_processor.ai.chapter_analysis import (
    LOCALIZED_PROCESSOR_VERSION,
    LOCALIZED_PROMPT_VERSION,
    LOCALIZED_SYSTEM_PROMPT,
    MAX_OUTPUT_TOKENS,
    MAX_REQUEST_BYTES,
    MAX_WINDOW_BYTES,
    MAX_WINDOWS,
    OUTPUT_SCHEMA,
    PROCESSOR_VERSION,
    PROMPT_NAME,
    PROMPT_VERSION,
    SYSTEM_PROMPT,
    ChapterAnalysis,
    OpenAIChapterAnalysisProvider,
)
from almonium_book_processor.ai.openai_provider import response_output_text
from almonium_book_processor.ai.output_language import (
    OutputLanguageError,
    validate_analysis_language,
)
from almonium_book_processor.catalog.ai_translation import TRANSLATION_MODEL_PRICING
from almonium_book_processor.catalog.models import (
    AIRun,
    Chapter,
    Edition,
    ModelConfiguration,
    PipelineRun,
    PromptTemplate,
    Work,
)

LEASE_DURATION = timedelta(minutes=10)


class AnalysisBusy(Exception):
    """Another worker still owns this run."""


class StaleAnalysis(ValueError):
    """The source changed while analysis was queued or running."""


class AnalysisRejected(ValueError):
    """A validated-but-unacceptable model answer; the message never contains book text."""


def _json(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _hash(value) -> str:
    return hashlib.sha256(_json(value).encode()).hexdigest()


def analysis_spec(language: str = "en") -> dict:
    # Reuse the deployed draft-model setting, but snapshot it independently.
    # No translation configuration or historical price row is mutated.
    localized = language != "en"
    return {
        "provider": "openai",
        "model": settings.OPENAI_TRANSLATION_DRAFT_MODEL,
        "pricing_per_million": TRANSLATION_MODEL_PRICING["draft"],
        "processor_version": LOCALIZED_PROCESSOR_VERSION if localized else PROCESSOR_VERSION,
        "prompt_version": LOCALIZED_PROMPT_VERSION if localized else PROMPT_VERSION,
        "system_prompt": LOCALIZED_SYSTEM_PROMPT if localized else SYSTEM_PROMPT,
        "output_schema": OUTPUT_SCHEMA,
        "reasoning_effort": "low",
        "max_output_tokens": MAX_OUTPUT_TOKENS,
        "window_bytes": MAX_WINDOW_BYTES,
        "request_bytes": MAX_REQUEST_BYTES,
        "max_windows": MAX_WINDOWS,
    }


def chapter_blocks(chapter: Chapter) -> list[dict]:
    """The nonblank text blocks a chapter is analyzed from, in their stored order."""
    return [
        {"block_id": b.block_id, "text": b.text, "type": b.block_type}
        for b in chapter.blocks.all()
        if b.text.strip()
    ]


def chapter_hash(edition: Edition, chapter: Chapter, blocks: list[dict]) -> str:
    """Fingerprint of one chapter's analyzable text and identity, independent of the spec."""
    return _hash(
        [
            edition.source_sha256,
            edition.language,
            str(chapter.id),
            chapter.sequence,
            chapter.title,
            blocks,
        ]
    )


def current_chapter_hashes(edition: Edition) -> dict[str, str]:
    """Each chapter's fingerprint for the text as it is now, keyed by chapter id."""
    return {
        str(chapter.id): chapter_hash(edition, chapter, chapter_blocks(chapter))
        for chapter in edition.chapters.order_by("sequence").prefetch_related("blocks")
    }


def snapshot(edition: Edition, spec: dict) -> dict:
    if edition.work.visibility != Work.Visibility.PUBLIC:
        raise ValueError("Chapter analysis is currently available only for public editions.")
    if edition.withdrawal_requested_at:
        raise ValueError("This edition is being withdrawn.")
    if not edition.language:
        raise ValueError("Confirm the edition language before analysis.")
    windows = []
    chapters = []
    for chapter in edition.chapters.order_by("sequence").prefetch_related("blocks"):
        blocks = chapter_blocks(chapter)
        if not blocks:
            continue
        digest = chapter_hash(edition, chapter, blocks)
        parts, current = [], []
        for block in blocks:
            if len(_json([block]).encode()) > spec["window_bytes"]:
                raise ValueError(
                    f"Block {block['block_id']} exceeds the chapter-analysis window limit; "
                    "review its segmentation before analysis. No text was truncated."
                )
            if current and len(_json([*current, block]).encode()) > spec["window_bytes"]:
                parts.append(current)
                current = []
            current.append(block)
        if current:
            parts.append(current)
        chapters.append({"id": str(chapter.id), "hash": digest, "windows": len(parts)})
        for index, part in enumerate(parts, 1):
            data = {
                "language": edition.language,
                "chapter_id": str(chapter.id),
                "chapter_sequence": chapter.sequence,
                "chapter_title": chapter.title,
                "window": index,
                "window_count": len(parts),
                "partial": len(parts) > 1,
                "blocks": part,
            }
            if len(_json(data).encode()) > spec["request_bytes"]:
                raise ValueError("Chapter metadata exceeds the analysis request limit.")
            windows.append({"hash": _hash([spec, digest, data]), "data": data})
            if len(windows) > spec["max_windows"]:
                raise ValueError(
                    f"Analysis is limited to {spec['max_windows']} windows per edition."
                )
    if not windows:
        raise ValueError("No chapter text is available to analyze.")
    return {"hash": _hash([spec, chapters]), "chapters": chapters, "windows": windows}


def queue_analysis(edition_id: str) -> PipelineRun:
    """Snapshot inputs in HTTP; dispatch only after the queued record commits."""
    from almonium_book_processor.catalog.chapter_projections import enqueue_projection
    from almonium_book_processor.catalog.tasks import analyze_edition_chapters

    if not settings.OPENAI_API_KEY:
        raise ValueError("No OpenAI key is configured.")
    edition = Edition.objects.select_related("work").get(id=edition_id)
    spec = analysis_spec(edition.language)
    plan = snapshot(edition, spec)
    with transaction.atomic():
        run, _ = PipelineRun.objects.get_or_create(
            idempotency_key=f"{edition.id}:chapter-analysis:{plan['hash']}",
            defaults={
                "edition": edition,
                "stage": PipelineRun.Stage.CHAPTER_ANALYSIS,
                "processor_version": spec["processor_version"],
                "input_hash": plan["hash"],
                "summary": {
                    "spec": spec,
                    "chapters": len(plan["chapters"]),
                    "windows": len(plan["windows"]),
                    "completed_windows": 0,
                },
            },
        )
        run = PipelineRun.objects.select_for_update().get(id=run.id)
        # Re-dispatch queued runs too: a broker failure after commit is repairable.
        live = run.status == PipelineRun.Status.RUNNING and (
            run.updated_at > timezone.now() - LEASE_DURATION
        )
        if run.status == PipelineRun.Status.SUCCEEDED:
            enqueue_projection(str(run.id))
        if run.status != PipelineRun.Status.SUCCEEDED and not live:
            run.status = PipelineRun.Status.QUEUED
            run.error = ""
            run.finished_at = None
            run.save(update_fields=["status", "error", "finished_at", "updated_at"])

            def dispatch():
                try:
                    analyze_edition_chapters.delay(str(run.id))
                except Exception:
                    PipelineRun.objects.filter(id=run.id, status=PipelineRun.Status.QUEUED).update(
                        status=PipelineRun.Status.FAILED,
                        error="Could not reach the job queue. Use Analyze / resume to try again.",
                        finished_at=timezone.now(),
                        updated_at=timezone.now(),
                    )
                    raise ValueError("Could not reach the job queue. Please retry.") from None

            transaction.on_commit(dispatch)
    return run


def _configuration(spec: dict) -> tuple[ModelConfiguration, PromptTemplate]:
    values = {
        "provider": spec["provider"],
        "model": spec["model"],
        "purpose": PROMPT_NAME,
        "parameters": spec,
    }
    configuration, _ = ModelConfiguration.objects.get_or_create(
        name=f"chapter-analysis-{_hash(spec)[:32]}", defaults=values
    )
    prompt_values = {
        "purpose": PROMPT_NAME,
        "system_prompt": spec["system_prompt"],
        "user_template": "{chapter_json}",
        "output_schema": spec["output_schema"],
    }
    prompt, _ = PromptTemplate.objects.get_or_create(
        name=PROMPT_NAME,
        version=spec["prompt_version"],
        defaults={**prompt_values, "active": True},
    )
    if not configuration.enabled or not prompt.active:
        raise ValueError("Chapter analysis model or prompt is disabled.")
    if any(getattr(configuration, key) != value for key, value in values.items()) or any(
        getattr(prompt, key) != value for key, value in prompt_values.items()
    ):
        raise ValueError("Analysis configuration changed in place; create a new version.")
    return configuration, prompt


def _claim(run_id: str) -> tuple[PipelineRun, str] | None:
    with transaction.atomic():
        run = PipelineRun.objects.select_for_update().filter(id=run_id).first()
        if run is None or run.status == PipelineRun.Status.SUCCEEDED:
            return None
        if run.stage != PipelineRun.Stage.CHAPTER_ANALYSIS:
            raise ValueError("Not a chapter-analysis run.")
        if (
            run.status == PipelineRun.Status.RUNNING
            and run.updated_at > timezone.now() - LEASE_DURATION
        ):
            raise AnalysisBusy("Chapter analysis is already running.")
        token = uuid.uuid4().hex
        run.status = PipelineRun.Status.RUNNING
        run.started_at = timezone.now()
        run.finished_at = None
        run.error = ""
        run.summary = {**run.summary, "lease": token}
        run.save()
        run.ai_runs.filter(status=AIRun.Status.SUBMITTED).update(
            status=AIRun.Status.FAILED,
            error="Worker lease expired; provider usage may be unknown. Retrying is a new attempt.",
            finished_at=timezone.now(),
            updated_at=timezone.now(),
        )
        return run, token


def _update_run(run: PipelineRun, token: str, **fields) -> None:
    updated = PipelineRun.objects.filter(id=run.id, summary__lease=token).update(
        **fields, updated_at=timezone.now()
    )
    if not updated:
        raise StaleAnalysis("Analysis was removed or another worker took over.")


def _current_plan(run: PipelineRun, spec: dict) -> dict:
    edition = Edition.objects.select_related("work").filter(id=run.edition_id).first()
    if edition is None:
        raise StaleAnalysis("Edition was removed during analysis.")
    plan = snapshot(edition, spec)
    if plan["hash"] != run.input_hash:
        raise StaleAnalysis("Text or chapter metadata changed. Queue analysis for the new version.")
    return plan


def _locate(text: str, quote: str) -> tuple[int, int] | None:
    """Exact match first; then forgive stray or missing whitespace and letter case."""
    start = text.find(quote)
    if start >= 0:
        return start, start + len(quote)
    compact = "".join(quote.split())
    if not compact:
        return None
    pattern = r"\s*".join(re.escape(char) for char in compact)
    match = re.search(pattern, text, re.IGNORECASE)
    return (match.start(), match.end()) if match else None


def _verify_citations(result: ChapterAnalysis, data: dict) -> tuple[ChapterAnalysis, list, list]:
    """Drop citations the text cannot back; reject only when nothing verifiable remains.

    Quotes and surfaces are rewritten to the exact source substring so stored
    payloads never carry the model's spelling of the book.
    """
    blocks = {b["block_id"]: b["text"] for b in data["blocks"]}
    spans, notes = [], []
    evidence, hard_words = [], []
    for kind, items, keep in (
        ("evidence", result.evidence, evidence),
        ("hard word", result.hard_words, hard_words),
    ):
        for item in items:
            quote = getattr(item, "quote", None) or item.surface
            located = _locate(blocks.get(item.block_id, ""), quote)
            if located is None:
                notes.append(f"Dropped {kind} not found in block {item.block_id}.")
                continue
            start, end = located
            exact = blocks[item.block_id][start:end]
            field = "quote" if kind == "evidence" else "surface"
            keep.append(item.model_copy(update={field: exact}))
            spans.append({"block_id": item.block_id, "start": start, "end": end})
    if not evidence:
        raise AnalysisRejected("No cited evidence occurs in the analyzed text.")
    if any(len(s) > 100 for s in [*result.themes, *result.characters, *result.content_flags]):
        raise AnalysisRejected("Analysis labels exceed the output limit.")
    unsupported = []
    if result.content_flags and not any(e.dimension == "content" for e in evidence):
        unsupported = list(result.content_flags)
        notes.append("Content flags lack cited content evidence; kept as unsupported suggestions.")
    result = result.model_copy(
        update={
            "evidence": evidence,
            "hard_words": hard_words,
            "content_flags": [f for f in result.content_flags if f not in unsupported],
        }
    )
    return result, spans, [*notes, *(f"Unsupported content flag: {f}" for f in unsupported)]


def _record_response(ai_run: AIRun, response: dict, spec: dict) -> bool:
    """Save usage before parsing; purge and late responses must not resurrect text."""
    usage = response.get("usage") or {}
    inputs = usage.get("input_tokens", 0)
    outputs = usage.get("output_tokens", 0)
    cached = (usage.get("input_tokens_details") or {}).get("cached_tokens", 0)
    prices = spec["pricing_per_million"]
    cost = (
        Decimal(max(0, inputs - cached)) * Decimal(prices["input"])
        + Decimal(cached) * Decimal(prices["cached_input"])
        + Decimal(outputs) * Decimal(prices["output"])
    ) / Decimal(1_000_000)
    with transaction.atomic():
        current = AIRun.objects.select_for_update().get(id=ai_run.id)
        current.input_tokens = inputs
        current.cached_input_tokens = cached
        current.output_tokens = outputs
        current.reasoning_tokens = (usage.get("output_tokens_details") or {}).get(
            "reasoning_tokens", 0
        )
        current.estimated_cost_usd = cost if usage else None
        current.provider_request_id = response.get("id", "")
        current.save(update_fields=[*AIRun.USAGE_FIELDS, "provider_request_id", "updated_at"])
        return current.edition_id is not None


def _attempt(run: PipelineRun, window: dict, spec: dict, configuration, prompt, provider) -> AIRun:
    cached = (
        AIRun.objects.filter(
            edition_id=run.edition_id,
            input_hash=window["hash"],
            status=AIRun.Status.SUCCEEDED,
            prompt_template=prompt,
            model_configuration=configuration,
        )
        .order_by("created_at", "id")
        .first()
    )
    if cached:
        return cached
    ai_run = AIRun.objects.create(
        edition_id=run.edition_id,
        pipeline_run=run,
        input_hash=window["hash"],
        idempotency_key=f"chapter-analysis:{uuid.uuid4()}",
        model_configuration=configuration,
        prompt_template=prompt,
        status=AIRun.Status.SUBMITTED,
        started_at=timezone.now(),
        request_payload={"execution": "direct", "window": window["data"]},
    )
    body = {
        "model": spec["model"],
        "instructions": spec["system_prompt"],
        "input": _json(window["data"]),
        "reasoning": {"effort": spec["reasoning_effort"]},
        "max_output_tokens": spec["max_output_tokens"],
        "text": {
            "format": {
                "type": "json_schema",
                "name": "chapter_analysis",
                "strict": True,
                "schema": spec["output_schema"],
            }
        },
        "store": False,
    }
    try:
        response = (provider or OpenAIChapterAnalysisProvider()).respond(body)
        if not _record_response(ai_run, response, spec):
            raise StaleAnalysis("Edition was removed while the provider was responding.")
        if response.get("status") != "completed":
            raise ValueError("Provider response was incomplete or refused.")
        result = ChapterAnalysis.model_validate_json(response_output_text(response))
        validate_analysis_language(result, window["data"]["language"])
        result, spans, notes = _verify_citations(result, window["data"])
        _current_plan(run, spec)
        with transaction.atomic():
            current = AIRun.objects.select_for_update().get(id=ai_run.id)
            if current.edition_id is None:
                raise StaleAnalysis("Edition was removed during analysis.")
            current.status = AIRun.Status.SUCCEEDED
            current.response_payload = {
                "analysis": result.model_dump(mode="json"),
                "evidence_spans": spans,
                "validation_notes": notes,
            }
            current.finished_at = timezone.now()
            current.save(update_fields=["status", "response_payload", "finished_at", "updated_at"])
        return current
    except Exception as error:
        # Schema and provider exceptions can contain book text, so only our own
        # messages are stored verbatim; source-bearing payloads are handled by purge.
        data = window["data"]
        where = f"Chapter {data['chapter_sequence']} window {data['window']}/{data['window_count']}"
        if isinstance(error, (StaleAnalysis, AnalysisRejected, OutputLanguageError)):
            reason = str(error)
        else:
            reason = f"{type(error).__name__}: the answer did not complete validation."
        AIRun.objects.filter(id=ai_run.id).update(
            status=AIRun.Status.FAILED,
            error=f"{where}: {reason}",
            finished_at=timezone.now(),
            updated_at=timezone.now(),
        )
        if isinstance(error, StaleAnalysis):
            raise
        raise AnalysisRejected(f"{where}: {reason}") from None


def analyze_chapters(run_id: str, *, provider=None) -> None:
    from almonium_book_processor.catalog.chapter_projections import refresh_projections

    if PipelineRun.objects.filter(id=run_id, status=PipelineRun.Status.SUCCEEDED).exists():
        refresh_projections(run_id)
        return
    claimed = _claim(run_id)
    if claimed is None:
        return
    run, token = claimed
    spec = run.summary["spec"]
    try:
        plan = _current_plan(run, spec)
        configuration, prompt = _configuration(spec)
        refresh_projections(run_id, token=token)
        results = []
        for window in plan["windows"]:
            _current_plan(run, spec)
            _update_run(run, token, status=PipelineRun.Status.RUNNING)
            ai_run = _attempt(run, window, spec, configuration, prompt, provider)
            results.append(str(ai_run.id))
            run.summary = {**run.summary, "completed_windows": len(results), "results": results}
            _update_run(
                run,
                token,
                summary=run.summary,
                progress=int(100 * len(results) / len(plan["windows"])),
            )
            refresh_projections(run_id, token=token)
        _current_plan(run, spec)
        _update_run(run, token, status=PipelineRun.Status.SUCCEEDED, finished_at=timezone.now())
    except Exception as error:
        PipelineRun.objects.filter(id=run.id, summary__lease=token).update(
            status=(
                PipelineRun.Status.CANCELLED
                if isinstance(error, StaleAnalysis)
                else PipelineRun.Status.FAILED
            ),
            error=(
                str(error)
                if isinstance(error, StaleAnalysis)
                else f"{error if isinstance(error, AnalysisRejected) else type(error).__name__}"
                " — retry reuses validated windows."
            ),
            finished_at=timezone.now(),
            updated_at=timezone.now(),
        )
        raise
    # The descriptions changed; each companion's contents are translated from them.
    from almonium_book_processor.catalog.metadata_translation import queue_for_translations_of

    queue_for_translations_of(run.edition)


def analysis_context(edition: Edition) -> dict:
    """Only results for the exact current snapshot appear as current proposals."""
    if edition.work.visibility != Work.Visibility.PUBLIC:
        return {}
    run = edition.pipeline_runs.filter(stage=PipelineRun.Stage.CHAPTER_ANALYSIS).first()
    context = {
        "chapter_analysis_run": run,
        "chapter_analysis_enabled": bool(settings.OPENAI_API_KEY),
        "projection_state": "pending",
    }
    if not run:
        return context
    try:
        plan = snapshot(edition, analysis_spec(edition.language))
        current = edition.pipeline_runs.filter(
            stage=PipelineRun.Stage.CHAPTER_ANALYSIS,
            input_hash=plan["hash"],
        ).first()
        if current:
            run = current
            context["chapter_analysis_run"] = run
        stale = plan["hash"] != run.input_hash
    except (ValueError, KeyError):
        stale = True
    context["chapter_analysis_stale"] = stale
    context["chapter_analysis_results"] = (
        []
        if stale
        else AIRun.objects.filter(
            id__in=run.summary.get("results", []),
            edition=edition,
            status=AIRun.Status.SUCCEEDED,
        ).order_by("created_at")
    )
    from almonium_book_processor.catalog.chapter_projections import projection_context

    context.update(projection_context(edition, context))
    return context
