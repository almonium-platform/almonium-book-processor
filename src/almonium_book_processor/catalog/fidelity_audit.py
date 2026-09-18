"""Paid fidelity audit: adapted blocks read beside their source by a literary-editor prompt.

Two shapes share one ledger contract. A pilot audit reads a chapter sample's
output beside the snapshot it was generated from and hangs off the pilot run.
An edition audit reads every chapter of an adaptation beside its source
edition, keeps material findings as review items on the adaptation, and is one
of the two gates a level has to pass before the work's floor counts it.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from almonium_book_processor.ai.fidelity import (
    MAX_OUTPUT_TOKENS,
    OUTPUT_SCHEMA,
    PROMPT_NAME,
    PROMPT_VERSION,
    PURPOSE,
    SYSTEM_PROMPT,
    Review,
)
from almonium_book_processor.ai.openai_provider import OpenAIBatchProvider, response_output_text
from almonium_book_processor.catalog.adaptation import (
    PILOT_VERSIONS,
    digest,
    record_response,
    source_snapshot,
)
from almonium_book_processor.catalog.ai_translation import TRANSLATION_MODEL_PRICING
from almonium_book_processor.catalog.models import (
    AIRun,
    Edition,
    ModelConfiguration,
    PipelineRun,
    PromptTemplate,
    QAWarning,
)

AUDIT_VERSION = "fidelity-audit-v1"
FINDING_CODE = "adaptation_fidelity_finding"
SEVERITIES = ("material", "minor", "uncertain")
# A whole pilot-sized chapter (40,000 characters) pairs into well under this,
# so a sample is one request; a long chapter of a full edition splits by block.
WINDOW_BYTES = 160_000
LEASE_DURATION = timedelta(minutes=15)


def _json(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _hash(value) -> str:
    return hashlib.sha256(_json(value).encode()).hexdigest()


def audit_spec() -> dict:
    return {
        "provider": "openai",
        "model": settings.OPENAI_TRANSLATION_QUALITY_MODEL,
        "reasoning_effort": "high",
        "pricing_per_million": TRANSLATION_MODEL_PRICING["quality"],
        "prompt_name": PROMPT_NAME,
        "prompt_version": PROMPT_VERSION,
        "max_output_tokens": MAX_OUTPUT_TOKENS,
        "window_bytes": WINDOW_BYTES,
    }


def _configuration(spec: dict) -> tuple[ModelConfiguration, PromptTemplate]:
    configuration, _ = ModelConfiguration.objects.get_or_create(
        name=f"fidelity-audit-{_hash(spec)[:32]}",
        defaults={
            "provider": spec["provider"],
            "model": spec["model"],
            "purpose": PURPOSE,
            "parameters": spec,
        },
    )
    prompt, _ = PromptTemplate.objects.get_or_create(
        name=PROMPT_NAME,
        version=spec["prompt_version"],
        defaults={
            "purpose": PURPOSE,
            "system_prompt": SYSTEM_PROMPT,
            "user_template": "{pairs_json}",
            "output_schema": OUTPUT_SCHEMA,
            "active": True,
        },
    )
    if prompt.system_prompt != SYSTEM_PROMPT or prompt.output_schema != OUTPUT_SCHEMA:
        raise ValueError(
            f"Fidelity prompt v{spec['prompt_version']} is already saved with different text "
            "or schema. Bump PROMPT_VERSION instead of editing a saved prompt."
        )
    if not configuration.enabled or not prompt.active:
        raise ValueError("The fidelity audit model or prompt is disabled.")
    return configuration, prompt


def _windows(pairs: list[dict], spec: dict) -> list[list[dict]]:
    parts: list[list[dict]] = []
    current: list[dict] = []
    for pair in pairs:
        if len(_json([pair]).encode()) > spec["window_bytes"]:
            raise ValueError(f"Block {pair['block_id']} exceeds the fidelity audit window limit.")
        if current and len(_json([*current, pair]).encode()) > spec["window_bytes"]:
            parts.append(current)
            current = []
        current.append(pair)
    if current:
        parts.append(current)
    return parts


def _normalize(text: str) -> str:
    replacements = {"“": '"', "”": '"', "’": "'", "‘": "'", "—": "-"}
    for old, new in replacements.items():
        text = text.replace(old, new)
    return " ".join(text.split()).casefold()


def _quote(text: str) -> str:
    """The model tends to wrap its quotes in quotation marks; those are not part of the book."""

    return _normalize(text).strip("\"' ").rstrip(".,;:")


def _verified(review: Review, pairs: list[dict]) -> list[dict]:
    """Issues as dicts, each saying whether its quotes really occur in the texts."""

    by_id = {pair["block_id"]: pair for pair in pairs}
    issues = []
    for issue in review.issues:
        pair = by_id.get(issue.block_id)
        data = issue.model_dump()
        data["quote_verified"] = bool(
            pair
            and _quote(issue.source_quote)
            and _quote(issue.source_quote) in _normalize(pair["source"])
            and _quote(issue.adapted_quote) in _normalize(pair["adapted"])
        )
        issues.append(data)
    return issues


def _audit_window(run, window: dict, spec: dict, configuration, prompt, provider) -> AIRun:
    """One paid comparison of a block-pair window; a validated answer is reused verbatim."""

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
    body = {
        "model": spec["model"],
        "instructions": SYSTEM_PROMPT,
        "input": _json(window["data"]),
        "reasoning": {"effort": spec["reasoning_effort"]},
        "max_output_tokens": spec["max_output_tokens"],
        "store": False,
        "text": {
            "format": {
                "type": "json_schema",
                "name": "fidelity_review",
                "strict": True,
                "schema": OUTPUT_SCHEMA,
            }
        },
    }
    ai = AIRun.objects.create(
        edition_id=run.edition_id,
        pipeline_run=run,
        model_configuration=configuration,
        prompt_template=prompt,
        input_hash=window["hash"],
        idempotency_key=f"fidelity-audit:{uuid.uuid4()}",
        status=AIRun.Status.SUBMITTED,
        started_at=timezone.now(),
        request_payload={"body": body, "window": window["data"]},
    )
    try:
        response = (provider or OpenAIBatchProvider()).respond(body)
        record_response(ai.id, response)
        if response.get("status") != "completed":
            raise ValueError("Provider did not complete the audit; partial output is not accepted.")
        review = Review.model_validate_json(response_output_text(response))
        issues = _verified(review, window["data"]["blocks"])
        with transaction.atomic():
            current = AIRun.objects.select_for_update().get(pk=ai.id)
            if current.edition_id is None:
                raise ValueError("Edition was removed during the audit.")
            current.response_payload = {
                **current.response_payload,
                "review": {"issues": issues, "assessment": review.assessment},
            }
            current.status = AIRun.Status.SUCCEEDED
            current.finished_at = timezone.now()
            current.save(update_fields=["response_payload", "status", "finished_at", "updated_at"])
        return current
    except Exception as error:
        AIRun.objects.filter(pk=ai.id).update(
            status=AIRun.Status.FAILED, error=type(error).__name__, finished_at=timezone.now()
        )
        raise


def _review(results: list[AIRun], spec: dict, pair_count: int) -> dict:
    issues = [issue for r in results for issue in r.response_payload["review"]["issues"]]
    return {
        "prompt_version": spec["prompt_version"],
        "model": spec["model"],
        "blocks": pair_count,
        "issues": issues,
        "counts": {s: sum(i["severity"] == s for i in issues) for s in SEVERITIES},
        "assessment": " ".join(
            r.response_payload["review"]["assessment"].strip() for r in results
        ).strip(),
        "ai_run_ids": [str(r.id) for r in results],
        "cost_usd": str(sum((r.estimated_cost_usd or Decimal("0")) for r in results)),
    }


# ---------------------------------------------------------------------------
# Pilot audit: a chapter sample beside the snapshot it was generated from.


def audit_pilot(pilot_id, *, provider=None) -> dict:
    pilot = PipelineRun.objects.select_related("edition__work").get(pk=pilot_id)
    if pilot.processor_version not in PILOT_VERSIONS or pilot.status != "succeeded":
        raise ValueError("A completed chapter pilot is required.")
    if pilot.summary.get("source_edition_id") != str(pilot.edition_id):
        raise ValueError("Audit standalone pilots, not full-book generation chunks.")
    generation = AIRun.objects.get(pk=pilot.summary["ai_run_id"], edition=pilot.edition)
    source = generation.request_payload["source"]
    chapter = pilot.edition.chapters.get(pk=source["chapter_id"])
    if (
        digest(
            source_snapshot(
                chapter, pilot.summary.get("block_ids"), target_level=source["target_level"]
            )
        )
        != pilot.summary["source_hash"]
    ):
        raise ValueError("Pilot source changed; generate a current pilot first.")
    adapted = {b["block_id"]: b for b in generation.response_payload["adaptation"]["blocks"]}
    pairs = [
        {"block_id": b["block_id"], "source": b["text"], "adapted": adapted[b["block_id"]]["text"]}
        for b in source["blocks"]
        if adapted[b["block_id"]]["text"].strip()
    ]
    if not pairs:
        raise ValueError("No pilot text to audit.")
    spec = audit_spec()
    windows = [
        {
            "hash": _hash([spec, str(generation.id), part]),
            "data": {"language": pilot.edition.language, "blocks": part},
        }
        for part in _windows(pairs, spec)
    ]
    identity = _hash([spec, str(generation.id), pairs])
    run, _ = PipelineRun.objects.get_or_create(
        idempotency_key=f"{pilot.id}:fidelity-audit:{identity}",
        defaults={
            "edition": pilot.edition,
            "stage": PipelineRun.Stage.ADAPT,
            "processor_version": AUDIT_VERSION,
            "input_hash": identity,
            "summary": {"kind": "pilot", "pilot_id": str(pilot.id), "spec": spec},
        },
    )
    if run.status == PipelineRun.Status.SUCCEEDED:
        return run.summary["review"]
    if not PipelineRun.objects.filter(
        pk=run.id, status__in=[PipelineRun.Status.QUEUED, PipelineRun.Status.FAILED]
    ).update(status=PipelineRun.Status.RUNNING, started_at=timezone.now(), error=""):
        raise ValueError("Fidelity audit already running; inspect its ledger before retrying.")
    try:
        configuration, prompt = _configuration(spec)
        results = [
            _audit_window(run, window, spec, configuration, prompt, provider) for window in windows
        ]
        review = _review(results, spec, len(pairs))
        run.summary = {**run.summary, "review": review}
        run.status = PipelineRun.Status.SUCCEEDED
        run.finished_at = timezone.now()
        run.save(update_fields=["summary", "status", "finished_at", "updated_at"])
        pilot.summary = {**pilot.summary, "fidelity_audit": review}
        pilot.save(update_fields=["summary", "updated_at"])
        return review
    except Exception as error:
        PipelineRun.objects.filter(pk=run.id).update(
            status=PipelineRun.Status.FAILED,
            finished_at=timezone.now(),
            error=str(error)[:1000] if isinstance(error, ValueError) else type(error).__name__,
        )
        raise


# ---------------------------------------------------------------------------
# Edition audit: every chapter of an adaptation beside its source edition.


def edition_plan(edition: Edition, spec: dict) -> dict:
    """Pair every nonblank adapted block with the source block that shares its id."""

    if edition.edition_type != Edition.EditionType.ADAPTATION or not edition.source_edition_id:
        raise ValueError("Only an adaptation generated from a source edition can be audited.")
    source = edition.source_edition
    if source.language != edition.language:
        raise ValueError("A fidelity audit compares same-language editions.")
    if edition.withdrawal_requested_at:
        raise ValueError("This edition is being withdrawn.")
    originals = dict(source.blocks.values_list("block_id", "text"))
    chapters, windows = [], []
    for chapter in edition.chapters.order_by("sequence").prefetch_related("blocks"):
        pairs = []
        for block in sorted(chapter.blocks.all(), key=lambda b: b.sequence):
            if not block.text.strip():
                continue
            if block.block_id not in originals:
                raise ValueError(
                    f"Block {block.block_id} has no source block with the same id; "
                    "the audit needs block-for-block lineage."
                )
            pairs.append(
                {
                    "block_id": block.block_id,
                    "source": originals[block.block_id],
                    "adapted": block.text,
                }
            )
        if not pairs:
            continue
        chapter_hash = _hash([str(chapter.id), chapter.sequence, chapter.title, pairs])
        parts = _windows(pairs, spec)
        chapters.append(
            {
                "id": str(chapter.id),
                "sequence": chapter.sequence,
                "title": chapter.title,
                "hash": chapter_hash,
                "pairs": len(pairs),
                "windows": len(parts),
            }
        )
        for index, part in enumerate(parts, 1):
            data = {
                "language": edition.language,
                "chapter_sequence": chapter.sequence,
                "window": index,
                "window_count": len(parts),
                "blocks": part,
            }
            windows.append({"hash": _hash([spec, chapter_hash, data]), "data": data})
    if not windows:
        raise ValueError("The edition has no text to audit.")
    return {
        "hash": _hash([spec, [c["hash"] for c in chapters]]),
        "chapters": chapters,
        "windows": windows,
    }


def queue_edition_audit(edition_id) -> PipelineRun:
    from almonium_book_processor.catalog.tasks import audit_edition_fidelity

    if not settings.OPENAI_API_KEY:
        raise ValueError("Configure an OpenAI key to audit fidelity.")
    edition = Edition.objects.select_related("source_edition", "work").get(pk=edition_id)
    spec = audit_spec()
    plan = edition_plan(edition, spec)
    with transaction.atomic():
        run, _ = PipelineRun.objects.get_or_create(
            idempotency_key=f"{edition.id}:fidelity-audit:{plan['hash']}",
            defaults={
                "edition": edition,
                "stage": PipelineRun.Stage.ADAPT,
                "processor_version": AUDIT_VERSION,
                "input_hash": plan["hash"],
                "summary": {
                    "kind": "edition",
                    "spec": spec,
                    "chapters": len(plan["chapters"]),
                    "windows": len(plan["windows"]),
                    "completed_windows": 0,
                },
            },
        )
        run = PipelineRun.objects.select_for_update().get(pk=run.id)
        if run.status == PipelineRun.Status.SUCCEEDED:
            return run
        if run.status == PipelineRun.Status.RUNNING and (
            run.updated_at > timezone.now() - LEASE_DURATION
        ):
            return run
        run.status = PipelineRun.Status.QUEUED
        run.error = ""
        run.finished_at = None
        run.save(update_fields=["status", "error", "finished_at", "updated_at"])
        transaction.on_commit(lambda: audit_edition_fidelity.delay(str(run.id)))
    return run


def run_edition_audit(run_id, *, provider=None) -> None:
    if not PipelineRun.objects.filter(pk=run_id, status=PipelineRun.Status.QUEUED).update(
        status=PipelineRun.Status.RUNNING, started_at=timezone.now(), progress=1
    ):
        return
    run = PipelineRun.objects.select_related("edition__source_edition", "edition__work").get(
        pk=run_id
    )
    edition = run.edition
    spec = run.summary["spec"]
    try:
        plan = edition_plan(edition, spec)
        if plan["hash"] != run.input_hash:
            raise ValueError("The text changed after this audit was queued; queue it again.")
        configuration, prompt = _configuration(spec)
        results = []
        for window in plan["windows"]:
            results.append(_audit_window(run, window, spec, configuration, prompt, provider))
            run.summary = {
                **run.summary,
                "completed_windows": len(results),
                "results": [str(r.id) for r in results],
            }
            run.progress = int(95 * len(results) / len(plan["windows"]))
            run.save(update_fields=["summary", "progress", "updated_at"])
        if edition_plan(edition, spec)["hash"] != run.input_hash:
            raise ValueError("The text changed during the audit; queue it again.")
        review = _review(results, spec, sum(c["pairs"] for c in plan["chapters"]))
        with transaction.atomic():
            _record_findings(run, edition, review)
            run.summary = {**run.summary, "review": review}
            run.status = PipelineRun.Status.SUCCEEDED
            run.progress = 100
            run.finished_at = timezone.now()
            run.save(update_fields=["summary", "status", "progress", "finished_at", "updated_at"])
    except Exception as error:
        PipelineRun.objects.filter(pk=run_id).update(
            status=PipelineRun.Status.FAILED,
            finished_at=timezone.now(),
            error=str(error)[:1000] if isinstance(error, ValueError) else type(error).__name__,
        )
        raise
    from almonium_book_processor.catalog.adaptation_floor import refresh_adaptation_floor

    refresh_adaptation_floor(edition.work)


def _record_findings(run: PipelineRun, edition: Edition, review: dict) -> None:
    """Material findings become review items; an older audit's open items are superseded."""

    now = timezone.now()
    edition.warnings.filter(code=FINDING_CODE, resolved_at=None).exclude(
        source_ref__startswith=f"fidelity-audit:{run.id}:"
    ).update(resolved_at=now, resolved_by=None, updated_at=now)
    blocks = {b.block_id: b for b in edition.blocks.all()}
    for index, issue in enumerate(review["issues"]):
        if issue["severity"] != "material":
            continue
        block = blocks.get(issue["block_id"])
        QAWarning.objects.update_or_create(
            edition=edition,
            code=FINDING_CODE,
            source_ref=f"fidelity-audit:{run.id}:{index}",
            defaults={
                "pipeline_run": run,
                "block": block,
                "severity": QAWarning.Severity.WARNING,
                "message": (
                    f"Block {issue['block_id']}: {issue['explanation']} "
                    f"Source: “{issue['source_quote']}” Adapted: “{issue['adapted_quote']}” "
                    f"Suggested: {issue['suggested_correction']}"
                    + ("" if issue["quote_verified"] else " (quotes not found verbatim)")
                ),
                "resolved_at": None,
                "resolved_by": None,
            },
        )


def audit_context(edition: Edition) -> dict:
    """The audit as it stands for the text as it is now."""

    context = {
        "fidelity_audit_run": None,
        "fidelity_audit_state": "none",
        "fidelity_audit_enabled": bool(settings.OPENAI_API_KEY),
        "fidelity_open_findings": 0,
    }
    if edition.edition_type != Edition.EditionType.ADAPTATION:
        return context
    latest = edition.pipeline_runs.filter(processor_version=AUDIT_VERSION).first()
    if latest is None:
        return context
    try:
        plan = edition_plan(edition, audit_spec())
    except ValueError:
        context.update(fidelity_audit_run=latest, fidelity_audit_state="stale")
        return context
    current = edition.pipeline_runs.filter(
        processor_version=AUDIT_VERSION, input_hash=plan["hash"]
    ).first()
    run = current or latest
    context["fidelity_audit_run"] = run
    if current is None:
        context["fidelity_audit_state"] = "stale"
    elif run.status == PipelineRun.Status.SUCCEEDED:
        context["fidelity_audit_state"] = "current"
    elif run.status in (PipelineRun.Status.QUEUED, PipelineRun.Status.RUNNING):
        context["fidelity_audit_state"] = run.status
    else:
        context["fidelity_audit_state"] = "failed"
    context["fidelity_open_findings"] = edition.warnings.filter(
        code=FINDING_CODE, resolved_at=None
    ).count()
    context["fidelity_secondary_findings"] = [
        issue
        for issue in (run.summary.get("review") or {}).get("issues", [])
        if issue["severity"] != "material"
    ]
    return context


def fidelity_gate(edition: Edition) -> tuple[bool, PipelineRun | None]:
    """Whether the current text has a completed audit with no open material findings."""

    context = audit_context(edition)
    passed = context["fidelity_audit_state"] == "current" and not context["fidelity_open_findings"]
    return passed, context["fidelity_audit_run"]
