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
import re
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
from almonium_book_processor.ai.output_language import validate_rewritten_language
from almonium_book_processor.catalog.adaptation import (
    PILOT_VERSIONS,
    digest,
    source_snapshot,
)
from almonium_book_processor.catalog.ai_translation import TRANSLATION_MODEL_PRICING
from almonium_book_processor.catalog.models import (
    AIRun,
    Edition,
    ModelConfiguration,
    PipelineRun,
    PromptTemplate,
    TextQualityFinding,
)

AUDIT_VERSION = "fidelity-audit-v1"
SEVERITIES = ("material", "minor", "uncertain")
# Every finding is a reviewable text-quality finding the editor applies or
# dismisses, never a note to acknowledge. Only material ones hold the gate.
FINDING_PREFIX = "fidelity_"
FINDING_CODES = {severity: f"{FINDING_PREFIX}{severity}" for severity in SEVERITIES}
CONFIDENCE = {"material": 0.9, "minor": 0.6, "uncertain": 0.3}
# A whole pilot-sized chapter (40,000 characters) pairs into well under this,
# so a sample is one request; a long chapter of a full edition splits by block.
WINDOW_BYTES = 160_000
LEASE_DURATION = timedelta(minutes=15)


def _json(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _hash(value) -> str:
    return hashlib.sha256(_json(value).encode()).hexdigest()


def audit_spec(tier: str | None = None) -> dict:
    tier = tier or settings.OPENAI_FIDELITY_TIER
    if tier not in TRANSLATION_MODEL_PRICING:
        raise ValueError("The fidelity audit tier must be 'quality' or 'draft'.")
    return {
        "provider": "openai",
        "tier": tier,
        "model": (
            settings.OPENAI_TRANSLATION_QUALITY_MODEL
            if tier == "quality"
            else settings.OPENAI_TRANSLATION_DRAFT_MODEL
        ),
        "reasoning_effort": "high",
        "pricing_per_million": TRANSLATION_MODEL_PRICING[tier],
        "prompt_name": PROMPT_NAME,
        "prompt_version": PROMPT_VERSION,
        "max_output_tokens": MAX_OUTPUT_TOKENS,
        "window_bytes": WINDOW_BYTES,
    }


def _identity(spec: dict) -> dict:
    """What can change an answer: model, effort, prompt. Prices and tier names cannot."""

    return {
        "model": spec["model"],
        "reasoning_effort": spec["reasoning_effort"],
        "prompt_version": spec["prompt_version"],
        "window_bytes": spec["window_bytes"],
    }


def _configuration(spec: dict) -> tuple[ModelConfiguration, PromptTemplate]:
    configuration, _ = ModelConfiguration.objects.get_or_create(
        name=f"fidelity-audit-{_hash(_identity(spec))[:32]}",
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


def _record_usage(ai_id, response: dict, spec: dict) -> None:
    usage = response.get("usage") or {}
    inputs = usage.get("input_tokens", 0)
    cached = (usage.get("input_tokens_details") or {}).get("cached_tokens", 0)
    outputs = usage.get("output_tokens", 0)
    prices = spec["pricing_per_million"]
    cost = (
        Decimal(max(0, inputs - cached)) * Decimal(prices["input"])
        + Decimal(cached) * Decimal(prices["cached_input"])
        + Decimal(outputs) * Decimal(prices["output"])
    ) / Decimal(1_000_000)
    with transaction.atomic():
        ai = AIRun.objects.select_for_update().get(pk=ai_id)
        ai.add_attempt_usage(
            input_tokens=inputs,
            cached_input_tokens=cached,
            output_tokens=outputs,
            reasoning_tokens=(usage.get("output_tokens_details") or {}).get("reasoning_tokens", 0),
            estimated_cost_usd=cost,
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
        _record_usage(ai.id, response, spec)
        if response.get("status") != "completed":
            raise ValueError("Provider did not complete the audit; partial output is not accepted.")
        review = Review.model_validate_json(response_output_text(response))
        issues = _verified(review, window["data"]["blocks"])
        # A correction is text an editor may write into the book; the audit
        # itself may explain in any language, so only the corrections are gated.
        validate_rewritten_language(
            [usable_suggestion(issue.suggested_correction) for issue in review.issues],
            window["data"]["language"],
        )
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
            "hash": _hash([_identity(spec), str(generation.id), part]),
            "data": {"language": pilot.edition.language, "blocks": part},
        }
        for part in _windows(pairs, spec)
    ]
    identity = _hash([_identity(spec), str(generation.id), pairs])
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
            windows.append({"hash": _hash([_identity(spec), chapter_hash, data]), "data": data})
    if not windows:
        raise ValueError("The edition has no text to audit.")
    return {
        "hash": _hash([_identity(spec), [c["hash"] for c in chapters]]),
        "chapters": chapters,
        "windows": windows,
    }


def queue_edition_audit(edition_id, *, tier: str | None = None, record: bool = True) -> PipelineRun:
    """Queue the audit of an edition's current text.

    A run with ``record=False`` is a comparison: it reads the same text under
    another tier and keeps its review in the ledger, but writes no findings
    and never counts as the edition's audit.
    """

    from almonium_book_processor.catalog.tasks import audit_edition_fidelity

    if not settings.OPENAI_API_KEY:
        raise ValueError("Configure an OpenAI key to audit fidelity.")
    edition = Edition.objects.select_related("source_edition", "work").get(pk=edition_id)
    spec = audit_spec(tier)
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
                    "kind": "edition" if record else "comparison",
                    "spec": spec,
                    "chapters": len(plan["chapters"]),
                    "chapter_hashes": {c["id"]: c["hash"] for c in plan["chapters"]},
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
            if run.summary.get("kind") == "edition":
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


def _words(text: str) -> list[tuple[int, int]]:
    return [(m.start(), m.end()) for m in re.finditer(r"\S+", text)]


def _same(a: str, b: str) -> bool:
    return _normalize(a).strip(".,;:!?\"'") == _normalize(b).strip(".,;:!?\"'")


INSTRUCTION = re.compile(r"^(use|replace|change|consider|keep|rewrite|delete|remove|omit)\b", re.I)


def usable_suggestion(suggestion: str) -> str:
    """The correction as text to write in, or empty when the editor wrote advice instead."""

    suggestion = _bare(suggestion)
    if not suggestion or INSTRUCTION.match(suggestion) or suggestion.count('"') >= 2:
        return ""
    return suggestion


def replacement_span(text: str, start: int, end: int, suggestion: str) -> tuple[int, int, str]:
    """The stretch of ``text`` the suggestion really rewrites, and the words to write in.

    The editor prompt quotes a few words but often writes its correction for
    the whole clause around them. Pasting the correction over the quote alone
    duplicates the words on either side ("blow us quickly blow us quickly").
    So the span grows outward while the suggestion's leading words match the
    words just before it and its trailing words match the words just after,
    or to the sentence's edge when the correction rewrites it from its first
    or through its last words. Punctuation and quotation marks at the span's
    edges belong to the sentence: they stay, and the correction's own closing
    mark is dropped when the text already supplies one.
    """

    words = _words(text)
    suggested = suggestion.split()
    before = [w for w in words if w[1] <= start]
    after = [w for w in words if w[0] >= end]
    inner = len([w for w in words if w[0] >= start and w[1] <= end])
    lead = 0
    for n in range(1, min(len(before), len(suggested) - inner) + 1):
        window = " ".join(text[a:b] for a, b in before[-n:])
        if _same(" ".join(suggested[:n]), window):
            lead = n
    if lead:
        start = before[-lead][0]
    s_start, s_end = _sentence_bounds(text, start, end)
    opening = [w for w in words if s_start <= w[0] < start][:3]
    if (
        not lead
        and len(opening) == 3
        and _same(" ".join(suggested[:3]), " ".join(text[a:b] for a, b in opening))
    ):
        start = s_start
    trail = 0
    for n in range(1, min(len(after), len(suggested) - inner - lead) + 1):
        window = " ".join(text[a:b] for a, b in after[:n])
        if _same(" ".join(suggested[-n:]), window):
            trail = n
    if trail:
        end = after[trail - 1][1]
    closing = [w for w in words if end < w[1] <= s_end][-3:]
    if (
        not trail
        and len(closing) == 3
        and _same(" ".join(suggested[-3:]), " ".join(text[a:b] for a, b in closing))
    ):
        end = s_end
    # Edges: the text keeps its opening quote, its closing mark and its closing quote.
    leading = re.match(r"[\"\u201c\u2018'(]+", text[start:end])
    if leading and not re.match(r"[\"\u201c\u2018'(]", suggestion):
        start += len(leading.group())
    trailing = re.search(r"[.!?,;:]*[\"\u201d\u2019')]*$", text[start:end])
    if trailing and trailing.group():
        end -= len(trailing.group())
    if re.search(r"[.!?,;:]$", suggestion) and (
        (trailing and trailing.group())
        or re.match(r"[.!?,;:\"\u201d\u2019')]", text[end : end + 1])
    ):
        suggestion = suggestion.rstrip(".!?,;:")
    return start, end, suggestion


def _record_findings(run: PipelineRun, edition: Edition, review: dict) -> None:
    """Every issue becomes a finding to apply or dismiss; older runs' open ones are superseded."""

    from almonium_book_processor.catalog.chapter_analysis import _locate

    edition.text_quality_findings.filter(
        status=TextQualityFinding.Status.OPEN, code__startswith=FINDING_PREFIX
    ).exclude(input_hash=run.input_hash).update(
        status=TextQualityFinding.Status.SUPERSEDED, updated_at=timezone.now()
    )
    blocks = {b.block_id: b for b in edition.blocks.all()}
    for issue in review["issues"]:
        block = blocks.get(issue["block_id"])
        if block is None:
            continue
        located = (
            _locate(block.text, _bare(issue["adapted_quote"])) if issue["quote_verified"] else None
        )
        suggested = usable_suggestion(issue["suggested_correction"])
        if located and suggested:
            *located, suggested = replacement_span(block.text, located[0], located[1], suggested)
        start, end = located if located else (None, None)
        fingerprint = _hash(
            [issue["block_id"], issue["source_quote"], issue["adapted_quote"], issue["explanation"]]
        )
        # A re-read of unchanged text, or a window carried over its own applied
        # suggestion, repeats the same issue: what the editor already applied is
        # done, and what they dismissed stays dismissed rather than reopening.
        settled_before = (
            edition.text_quality_findings.filter(
                fingerprint=fingerprint,
                status__in=[
                    TextQualityFinding.Status.DISMISSED,
                    TextQualityFinding.Status.APPLIED,
                ],
            )
            .order_by("-reviewed_at")
            .first()
        )
        if settled_before and settled_before.status == TextQualityFinding.Status.APPLIED:
            continue
        dismissed_before = settled_before
        TextQualityFinding.objects.update_or_create(
            edition=edition,
            input_hash=run.input_hash,
            fingerprint=fingerprint,
            defaults={
                "pipeline_run": run,
                "block": block,
                "stable_block_id": block.block_id,
                "code": FINDING_CODES[issue["severity"]],
                "status": (
                    TextQualityFinding.Status.DISMISSED
                    if dismissed_before
                    else TextQualityFinding.Status.OPEN
                ),
                "reviewed_by": dismissed_before.reviewed_by if dismissed_before else None,
                "reviewed_at": dismissed_before.reviewed_at if dismissed_before else None,
                "start_offset": start,
                "end_offset": end,
                "original_text": block.text[start:end]
                if located
                else _bare(issue["adapted_quote"]),
                "suggested_text": suggested if located and suggested else "",
                "confidence": CONFIDENCE[issue["severity"]],
                "message": issue["explanation"],
                "evidence": {
                    "severity": issue["severity"],
                    "source_quote": _bare(issue["source_quote"]),
                    "adapted_quote": _bare(issue["adapted_quote"]),
                    "suggested_correction": suggested,
                    "quote_verified": issue["quote_verified"],
                    "audit_run_id": str(run.id),
                },
            },
        )


def _bare(text: str) -> str:
    """A quote or correction without the quotation marks the model wraps it in."""

    text = " ".join(text.split())
    for old, new in {"\u201c": '"', "\u201d": '"', "\u2019": "'", "\u2018": "'"}.items():
        text = text.replace(old, new)
    return text.strip("\"' ")


def excerpt(text: str, quote: str, *, whole: bool = False) -> tuple[str, str, str]:
    """The sentence around ``quote`` in ``text`` as (before, span, after), or the whole text.

    When the quote cannot be placed the text comes back unmarked in ``before``.
    """

    from almonium_book_processor.catalog.chapter_analysis import _locate

    located = _locate(text, _bare(quote)) if quote else None
    if located is None:
        # A quote with ellipses names several spans; the longest piece places it well enough.
        pieces = sorted(
            (piece.strip(" ,;") for piece in re.split(r"\.\.\.|\u2026", _bare(quote or ""))),
            key=len,
            reverse=True,
        )
        for piece in pieces:
            if len(piece) >= 8 and (located := _locate(text, piece)) is not None:
                break
    if located is None:
        return (text if whole or len(text) <= 320 else text[:300].rsplit(" ", 1)[0] + " …"), "", ""
    start, end = located
    if whole:
        return text[:start], text[start:end], text[end:]
    left = max((text.rfind(stop, 0, start) for stop in (". ", "! ", "? ", ".\n")), default=-1)
    left = 0 if left < 0 else left + 2
    rights = [i for i in (text.find(stop, end) for stop in (". ", "! ", "? ")) if i >= 0]
    right = min(rights) + 1 if rights else len(text)
    return text[left:start], text[start:end], text[end:right]


def _fragments(quote: str) -> list[str]:
    """The pieces of a quote the model wrote with ellipses, longest first."""

    pieces = (piece.strip(" ,;") for piece in re.split(r"\.\.\.|\u2026", _bare(quote or "")))
    return sorted((p for p in pieces if len(p) >= 8), key=len, reverse=True)


def _sentence_bounds(text: str, start: int, end: int) -> tuple[int, int]:
    left = max((text.rfind(stop, 0, start) for stop in (". ", "! ", "? ", ".\n")), default=-1)
    left = 0 if left < 0 else left + 2
    rights = [i for i in (text.find(stop, end) for stop in (". ", "! ", "? ")) if i >= 0]
    return left, (min(rights) + 1 if rights else len(text))


def side_excerpt(text: str, quote: str, counterpart: str = "") -> list[dict]:
    """One side of a finding: the sentences that hold any quoted words, the finding's own marked.

    The counterpart quote is searched too, unmarked, so that when an adaptation
    split one source sentence into two, both halves show and the two sides
    line up. Text that holds no quoted words shows its first three hundred
    characters, so a reviewer still sees where they are.
    """

    from almonium_book_processor.catalog.chapter_analysis import _locate

    marked, plain = [], []
    for fragments, keep in ((_fragments(quote), marked), (_fragments(counterpart), plain)):
        for fragment in fragments:
            located = _locate(text, fragment)
            if located and not any(a <= located[0] < b for a, b in [*marked, *plain]):
                keep.append(located)
    spans = sorted([*marked, *plain])
    if not spans:
        short = text if len(text) <= 320 else text[:300].rsplit(" ", 1)[0] + " …"
        return [{"text": short, "marked": False}] if short else []
    bounds = [_sentence_bounds(text, a, b) for a, b in spans]
    left, right = min(b[0] for b in bounds), max(b[1] for b in bounds)
    segments, cursor = [], left
    for a, b in sorted(marked):
        if a < cursor:
            continue
        segments.append({"text": text[cursor:a], "marked": False})
        segments.append({"text": text[a:b], "marked": True})
        cursor = b
    segments.append({"text": text[cursor:right], "marked": False})
    return [s for s in segments if s["text"]]


def change_preview(text: str, quote: str, suggestion: str) -> tuple[list[dict], bool]:
    """The adapted sentence as it would read with the suggestion in: old span out, new wording in.

    Returns the segments and whether the suggestion could be placed; when it
    could not, the sentence the quote pointed at is struck as a whole and the
    suggestion follows it, so the reviewer still sees what would change.
    """

    before, span, after = excerpt(text, quote)
    suggestion = _bare(suggestion)
    if span:
        # The same span the apply will use: grown to the clause the correction rewrites.
        start = text.index(before + span + after) + len(before)
        s, e, words = replacement_span(text, start, start + len(span), suggestion)
        left, right = _sentence_bounds(text, s, e)
        segments = [
            {"op": "equal", "text": text[left:s]},
            {"op": "delete", "text": text[s:e]},
            {"op": "insert", "text": words},
            {"op": "equal", "text": text[e:right]},
        ]
    else:
        segments = [{"op": "delete", "text": before}, {"op": "insert", "text": " " + suggestion}]
    return [segment for segment in segments if segment["text"]], bool(span)


def open_findings(edition: Edition):
    return (
        edition.text_quality_findings.filter(
            status=TextQualityFinding.Status.OPEN, code__startswith=FINDING_PREFIX
        )
        .select_related("block__chapter")
        .order_by("-confidence", "block__chapter__sequence", "block__sequence", "start_offset")
    )


def carry_audit_forward(
    edition: Edition, findings, *, run: PipelineRun | None = None
) -> PipelineRun | None:
    """Keep the audit current after its own suggestions were written in verbatim.

    The auditor proposed the wording, so its verdict covers the text that now
    stands; re-reading twenty chapters to confirm the auditor's own words is
    money for nothing. The run is re-keyed to the new text and records which
    blocks it was carried over, so the trail from run to text stays honest.
    A hand edit or a changed replacement never carries: that text is unread.
    """

    findings = list(findings)
    if not findings:
        return None
    run = run or (
        edition.pipeline_runs.filter(
            processor_version=AUDIT_VERSION,
            summary__kind="edition",
            status=PipelineRun.Status.SUCCEEDED,
            input_hash=findings[0].input_hash,
        )
        .order_by("-created_at")
        .first()
    )
    if run is None:
        return None
    spec = run.summary["spec"]
    plan = edition_plan(edition, spec)
    old_hash = run.input_hash
    # The windows the run read follow it: a window whose chapter changed only by
    # the auditor's own words keeps its result under the new window hash, so a
    # later re-read pays for hand-edited chapters alone.
    known = set(
        AIRun.objects.filter(
            edition=edition,
            status=AIRun.Status.SUCCEEDED,
            input_hash__in=[w["hash"] for w in plan["windows"]],
        ).values_list("input_hash", flat=True)
    )
    read = {}
    for result in AIRun.objects.filter(
        id__in=run.summary.get("results", []), status=AIRun.Status.SUCCEEDED
    ):
        data = result.request_payload["window"]
        read[(data["chapter_sequence"], data["window"])] = result
    for window in plan["windows"]:
        if window["hash"] in known:
            continue
        data = window["data"]
        result = read.get((data["chapter_sequence"], data["window"]))
        if result is not None and result.input_hash not in known:
            AIRun.objects.filter(id=result.id).update(
                input_hash=window["hash"], updated_at=timezone.now()
            )
            known.add(window["hash"])
    carried = list(run.summary.get("carried") or [])
    carried.extend(
        {
            "block_id": f.stable_block_id,
            "finding_id": str(f.id),
            "at": timezone.now().isoformat(),
        }
        for f in findings
    )
    run.input_hash = plan["hash"]
    run.idempotency_key = f"{edition.id}:fidelity-audit:{plan['hash']}"
    run.summary = {
        **run.summary,
        "chapter_hashes": {c["id"]: c["hash"] for c in plan["chapters"]},
        "carried": carried,
    }
    run.save(update_fields=["input_hash", "idempotency_key", "summary", "updated_at"])
    edition.text_quality_findings.filter(
        code__startswith=FINDING_PREFIX, input_hash=old_hash
    ).update(input_hash=plan["hash"])
    return run


def relocate_fidelity_findings(edition: Edition, block_ids) -> None:
    """After a block changed, place its other open findings again instead of dropping them.

    A finding whose span is still in the text keeps working; one whose span is
    gone stays open without offsets, which the page shows as a hand edit.
    """

    from almonium_book_processor.catalog.chapter_analysis import _locate

    for finding in edition.text_quality_findings.filter(
        status=TextQualityFinding.Status.OPEN,
        code__startswith=FINDING_PREFIX,
        block_id__in=list(block_ids),
    ).select_related("block"):
        text = finding.block.text
        evidence = finding.evidence or {}
        quote = evidence.get("adapted_quote") or finding.original_text
        located = _locate(text, quote) if quote else None
        suggested = usable_suggestion(evidence.get("suggested_correction") or "")
        if located and suggested:
            *located, suggested = replacement_span(text, *located, suggested)
        if located:
            finding.start_offset, finding.end_offset = located
            finding.original_text = text[located[0] : located[1]]
            finding.suggested_text = suggested
        else:
            finding.start_offset = finding.end_offset = None
            finding.suggested_text = ""
        finding.save(
            update_fields=[
                "start_offset",
                "end_offset",
                "original_text",
                "suggested_text",
                "updated_at",
            ]
        )


def audit_context(edition: Edition) -> dict:
    """The audit as it stands for the text as it is now."""

    context = {
        "fidelity_audit_run": None,
        "fidelity_audit_state": "none",
        "fidelity_audit_enabled": bool(settings.OPENAI_API_KEY),
        "fidelity_open_findings": 0,
        "fidelity_findings": [],
        "fidelity_applicable": 0,
        "fidelity_counts": dict.fromkeys(SEVERITIES, 0),
    }
    if edition.edition_type != Edition.EditionType.ADAPTATION:
        return context
    audits = edition.pipeline_runs.filter(processor_version=AUDIT_VERSION, summary__kind="edition")
    latest = audits.first()
    if latest is None:
        return context
    try:
        plan = edition_plan(edition, audit_spec())
    except ValueError:
        context.update(fidelity_audit_run=latest, fidelity_audit_state="stale")
        return context
    current = audits.filter(input_hash=plan["hash"]).first()
    run = current or latest
    context["fidelity_audit_run"] = run
    if current is None:
        context["fidelity_audit_state"] = "stale"
        known = run.summary.get("chapter_hashes") or {}
        changed = [c for c in plan["chapters"] if known.get(c["id"]) != c["hash"]]
        context["fidelity_stale_chapters"] = len(changed)
        review = run.summary.get("review") or {}
        per_window = (
            Decimal(review["cost_usd"]) / max(1, run.summary.get("windows") or 1)
            if review.get("cost_usd")
            else Decimal("0")
        )
        context["fidelity_stale_cost"] = str(
            (per_window * sum(c["windows"] for c in changed)).quantize(Decimal("0.01"))
        )
    elif run.status == PipelineRun.Status.SUCCEEDED:
        context["fidelity_audit_state"] = "current"
    elif run.status in (PipelineRun.Status.QUEUED, PipelineRun.Status.RUNNING):
        context["fidelity_audit_state"] = run.status
    else:
        context["fidelity_audit_state"] = "failed"
    findings = list(open_findings(edition))
    dismissed = list(
        edition.text_quality_findings.filter(
            status=TextQualityFinding.Status.DISMISSED,
            code__startswith=FINDING_PREFIX,
            input_hash=run.input_hash,
        )
        .select_related("block__chapter")
        .order_by("-confidence", "block__chapter__sequence", "block__sequence")
    )
    originals = dict(
        edition.source_edition.blocks.filter(
            block_id__in={f.stable_block_id for f in [*findings, *dismissed]}
        ).values_list("block_id", "text")
    )
    for finding in [*findings, *dismissed]:
        # Both sides of the change, so the reviewer reads them here, not in the reader.
        finding.source_text = originals.get(finding.stable_block_id, "")
        finding.adapted_text = finding.block.text if finding.block else ""
    context["fidelity_findings"] = findings
    context["fidelity_dismissed"] = dismissed
    context["fidelity_manual"] = sum(not (f.can_apply and f.suggested_text) for f in findings)
    context["fidelity_counts"] = {
        severity: sum(f.code == FINDING_CODES[severity] for f in findings)
        for severity in SEVERITIES
    }
    context["fidelity_open_findings"] = context["fidelity_counts"]["material"]
    context["fidelity_applicable"] = sum(f.can_apply and bool(f.suggested_text) for f in findings)
    context["fidelity_carried"] = len(run.summary.get("carried") or [])
    return context


def fidelity_gate(edition: Edition) -> tuple[bool, PipelineRun | None]:
    """Whether the current text has a completed audit with no open material findings."""

    context = audit_context(edition)
    passed = context["fidelity_audit_state"] == "current" and not context["fidelity_open_findings"]
    return passed, context["fidelity_audit_run"]
