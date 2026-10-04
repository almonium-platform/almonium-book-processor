"""Worker-side, bounded blind assessment of a saved adaptation pilot."""

from decimal import Decimal

from django.conf import settings
from django.utils import timezone

from almonium_book_processor.ai.pricing import has_price, seat_prices
from almonium_book_processor.ai.seats import parse_seat, provider_for
from almonium_book_processor.catalog.adaptation import PILOT_VERSIONS
from almonium_book_processor.catalog.chapter_analysis import (
    AnalysisRejected,
    _attempt,
    _configuration,
    _hash,
    _json,
    analysis_spec,
    snapshot,
)
from almonium_book_processor.catalog.chapter_projections import LEVELS, percentile
from almonium_book_processor.catalog.models import AIRun, PipelineRun


def judge_specs(language: str) -> list[dict]:
    """The blind judges of a pilot, each as the analysis spec it reads with.

    With no seats configured the judge is the chapter-analysis model alone, with the spec
    every past assessment was saved under.
    """

    base = analysis_spec(language)
    if not settings.DIFFICULTY_JUDGES:
        return [base]
    specs = []
    for setting in settings.DIFFICULTY_JUDGES.split(","):
        seat = parse_seat(setting)
        if not has_price(seat.model):
            raise ValueError(f"No price is known for {seat.model}; add it to ai/pricing.py")
        specs.append(
            {
                **base,
                "provider": seat.provider,
                "model": seat.model,
                "pricing_per_million": seat_prices(seat.provider, seat.model),
                "reasoning_effort": seat.effort or base["reasoning_effort"],
            }
        )
    return specs


def judge_readings() -> int:
    """How often each judge reads: a judge's single reading wavers at a level's boundary."""

    return max(1, settings.DIFFICULTY_READINGS) if settings.DIFFICULTY_JUDGES else 1


def judge_label(language: str) -> str:
    """The judges by name, as an assessment and a probe record who judged."""

    return " + ".join(spec["model"] for spec in judge_specs(language))


def _middle(levels: list[str]) -> str:
    """The middle reading; of an even number, the higher of the two in the middle."""

    return sorted(levels, key=LEVELS.index)[len(levels) // 2]


def _read(run, window, spec, configuration, prompt, provider) -> AIRun:
    """One reading of one window. A rejected answer is asked for once more.

    A judge is rejected when it cites words that are not in the text. A panel makes many
    calls for one pilot, and one bad answer should cost a call, not the whole assessment.
    """

    try:
        return _attempt(run, window, spec, configuration, prompt, provider, reader_facing=False)
    except AnalysisRejected:
        return _attempt(run, window, spec, configuration, prompt, provider, reader_facing=False)


def _judge(pilot, generation, chapter, parts, blocks, spec, readings, provider) -> dict:
    """One judge's assessment: every window read ``readings`` times, the middle reading kept."""

    plan = snapshot(pilot.edition, spec)
    # A single reading keeps the identity past assessments were saved under.
    identity = _hash([generation.input_hash, spec, blocks] + ([readings] if readings > 1 else []))
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
    if not PipelineRun.objects.filter(
        pk=run.id, status__in=[PipelineRun.Status.QUEUED, PipelineRun.Status.FAILED]
    ).update(status=PipelineRun.Status.RUNNING, started_at=timezone.now(), error=""):
        raise ValueError("Assessment already running; inspect its ledger before retrying.")
    try:
        configuration, prompt = _configuration(spec)
        if provider is None and spec["provider"] != "openai":
            provider = provider_for(spec["provider"], spec["model"])
        taken = []
        for reading in range(1, readings + 1):
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
                # a later reading is a new call, not the first one's cached answer
                key = [identity, data] if reading == 1 else [identity, data, reading]
                window = {"hash": _hash(key), "data": data}
                results.append(_read(run, window, spec, configuration, prompt, provider))
            levels = [r.response_payload["analysis"]["cefr_estimate"] for r in results]
            taken.append({"results": results, "max_level": max(levels, key=LEVELS.index)})
        level = _middle([reading["max_level"] for reading in taken])
        # the reading that stands for the judge: the first whose highest window is its level
        kept = next(reading for reading in taken if reading["max_level"] == level)["results"]
        runs = [r for reading in taken for r in reading["results"]]
        assessment = {
            "prompt_version": spec["prompt_version"],
            "model": spec["model"],
            "cefr_estimate": percentile(
                [r.response_payload["analysis"]["cefr_estimate"] for r in kept],
                [sum(len(b["text"].split()) for b in p) for p in parts],
            ),
            "max_level": level,
            "ai_run_ids": [str(r.id) for r in runs],
            "windows": [r.response_payload["analysis"] for r in kept],
            "cost_usd": str(sum(r.estimated_cost_usd or 0 for r in runs)),
            **({"readings": [reading["max_level"] for reading in taken]} if readings > 1 else {}),
        }
        run.summary = {**run.summary, "assessment": assessment}
        run.status = PipelineRun.Status.SUCCEEDED
        run.finished_at = timezone.now()
        run.save(update_fields=["summary", "status", "finished_at", "updated_at"])
        return assessment
    except Exception:
        PipelineRun.objects.filter(pk=run.id).update(
            status=PipelineRun.Status.FAILED,
            finished_at=timezone.now(),
            error="Pilot assessment failed; inspect AI ledger.",
        )
        raise


def assess_pilot(pilot_id, *, provider=None):
    """Judge a pilot's text blind; the highest of the judges' levels is the pilot's.

    ``provider`` stands in for every judge's own, for tests.
    """

    pilot = PipelineRun.objects.select_related("edition__work").get(pk=pilot_id)
    if pilot.processor_version not in PILOT_VERSIONS or pilot.status != "succeeded":
        raise ValueError("A completed chapter pilot is required.")
    generation = AIRun.objects.get(pk=pilot.summary["ai_run_id"], edition=pilot.edition)
    specs = judge_specs(pilot.edition.language)
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
    window_bytes = specs[0]["window_bytes"]
    parts, current = [], []
    for block in blocks:
        if len(_json([block]).encode()) > window_bytes:
            raise ValueError("Pilot block exceeds the judge window limit.")
        if current and len(_json([*current, block]).encode()) > window_bytes:
            parts.append(current)
            current = []
        current.append(block)
    if current:
        parts.append(current)
    if not parts:
        raise ValueError("No pilot text to assess.")
    readings = judge_readings()
    verdicts = [
        _judge(pilot, generation, chapter, parts, blocks, spec, readings, provider)
        for spec in specs
    ]
    # The strictest judge decides, and its windows are the evidence shown.
    decisive = max(verdicts, key=lambda verdict: LEVELS.index(verdict["max_level"]))
    assessment = {
        "prompt_version": decisive["prompt_version"],
        "model": judge_label(pilot.edition.language),
        "cefr_estimate": decisive["cefr_estimate"],
        "max_level": decisive["max_level"],
        "ai_run_ids": [run_id for verdict in verdicts for run_id in verdict["ai_run_ids"]],
        "windows": decisive["windows"],
        "cost_usd": str(sum((Decimal(verdict["cost_usd"]) for verdict in verdicts), Decimal(0)))
        if len(verdicts) > 1
        else decisive["cost_usd"],
        **(
            {
                "judges": [
                    {
                        "model": verdict["model"],
                        "level": verdict["max_level"],
                        "readings": verdict.get("readings", [verdict["max_level"]]),
                    }
                    for verdict in verdicts
                ]
            }
            if len(verdicts) > 1 or readings > 1
            else {}
        ),
    }
    pilot.summary = {**pilot.summary, "difficulty_check": assessment}
    pilot.save(update_fields=["summary", "updated_at"])
    return assessment
