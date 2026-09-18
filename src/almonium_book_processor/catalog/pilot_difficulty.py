"""Worker-side, bounded blind assessment of a saved adaptation pilot."""

from django.utils import timezone

from almonium_book_processor.catalog.adaptation import PILOT_VERSIONS
from almonium_book_processor.catalog.chapter_analysis import (
    _attempt,
    _configuration,
    _hash,
    _json,
    analysis_spec,
    snapshot,
)
from almonium_book_processor.catalog.chapter_projections import LEVELS, percentile
from almonium_book_processor.catalog.models import AIRun, PipelineRun


def assess_pilot(pilot_id, *, provider=None):
    pilot = PipelineRun.objects.select_related("edition__work").get(pk=pilot_id)
    if pilot.processor_version not in PILOT_VERSIONS or pilot.status != "succeeded":
        raise ValueError("A completed chapter pilot is required.")
    generation = AIRun.objects.get(pk=pilot.summary["ai_run_id"], edition=pilot.edition)
    spec = analysis_spec(pilot.edition.language)
    plan = snapshot(pilot.edition, spec)
    source = generation.request_payload["source"]
    if pilot.summary.get("source_edition_id") != str(pilot.edition_id):
        raise ValueError("Assess standalone pilots, not full-book generation chunks.")
    from almonium_book_processor.catalog.adaptation import digest, source_snapshot

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
    # No target, author, work title, generation prompt or judge's previous answer is supplied.
    blocks = [
        {"block_id": b["block_id"], "type": b["type"], "text": adapted[b["block_id"]]["text"]}
        for b in source["blocks"]
        if adapted[b["block_id"]]["text"].strip()
    ]
    parts, current = [], []
    for block in blocks:
        if len(_json([block]).encode()) > spec["window_bytes"]:
            raise ValueError("Pilot block exceeds the judge window limit.")
        if current and len(_json([*current, block]).encode()) > spec["window_bytes"]:
            parts.append(current)
            current = []
        current.append(block)
    if current:
        parts.append(current)
    if not parts:
        raise ValueError("No pilot text to assess.")
    identity = _hash([generation.input_hash, spec, blocks])
    run, _ = PipelineRun.objects.get_or_create(
        idempotency_key=f"{pilot.id}:pilot-difficulty:{identity}",
        defaults={
            "edition": pilot.edition,
            "stage": PipelineRun.Stage.ADAPT,
            "processor_version": "pilot-difficulty-v1",
            "input_hash": plan["hash"],
            "summary": {"pilot_id": str(pilot.id), "spec": spec},
        },
    )
    if run.status == PipelineRun.Status.SUCCEEDED:
        return run.summary["assessment"]
    if not PipelineRun.objects.filter(pk=run.id, status=PipelineRun.Status.QUEUED).update(
        status=PipelineRun.Status.RUNNING, started_at=timezone.now()
    ):
        raise ValueError(
            "Assessment already running or failed; inspect its ledger before retrying."
        )
    try:
        configuration, prompt = _configuration(spec)
        results = []
        for index, part in enumerate(parts, 1):
            data = {
                "language": pilot.edition.language,
                "chapter_sequence": chapter.sequence,
                "window": index,
                "window_count": len(parts),
                "partial": len(parts) > 1,
                "blocks": part,
            }
            window = {"hash": _hash([identity, data]), "data": data}
            results.append(_attempt(run, window, spec, configuration, prompt, provider))
        levels = [r.response_payload["analysis"]["cefr_estimate"] for r in results]
        assessment = {
            "prompt_version": spec["prompt_version"],
            "model": spec["model"],
            "cefr_estimate": percentile(
                levels, [sum(len(b["text"].split()) for b in p) for p in parts]
            ),
            "max_level": max(levels, key=LEVELS.index),
            "ai_run_ids": [str(r.id) for r in results],
            "windows": [r.response_payload["analysis"] for r in results],
            "cost_usd": str(sum(r.estimated_cost_usd or 0 for r in results)),
        }
        run.summary = {**run.summary, "assessment": assessment}
        run.status = PipelineRun.Status.SUCCEEDED
        run.finished_at = timezone.now()
        run.save(update_fields=["summary", "status", "finished_at", "updated_at"])
        pilot.summary = {**pilot.summary, "difficulty_check": assessment}
        pilot.save(update_fields=["summary", "updated_at"])
        return assessment
    except Exception:
        PipelineRun.objects.filter(pk=run.id).update(
            status=PipelineRun.Status.FAILED,
            finished_at=timezone.now(),
            error="Pilot assessment failed; inspect AI ledger.",
        )
        raise
