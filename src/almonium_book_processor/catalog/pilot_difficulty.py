"""Worker-side, bounded blind assessment of a saved adaptation pilot."""

from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.db.models import Q
from django.utils import timezone

from almonium_book_processor.ai.chapter_analysis import (
    LOCALIZED_WORDING_PROMPT_VERSION,
    WORDING_NOTE,
    WORDING_PROMPT_VERSION,
)
from almonium_book_processor.ai.cli_calls import AllowanceUsedUp, NetworkDown
from almonium_book_processor.ai.pricing import has_price, seat_prices
from almonium_book_processor.ai.seats import parse_seat, provider_for
from almonium_book_processor.catalog.adaptation import PILOT_VERSIONS
from almonium_book_processor.catalog.chapter_analysis import (
    CitationRejected,
    _attempt,
    _configuration,
    _hash,
    _json,
    analysis_spec,
    judged_blocks,
    snapshot,
    spec_identity,
)
from almonium_book_processor.catalog.chapter_projections import LEVELS, percentile
from almonium_book_processor.catalog.models import AIRun, PipelineRun

# A judge's reading of one chapter is a handful of calls; none takes this long.
ABANDONED = timedelta(minutes=45)


def judge_specs(language: str, *, wording: bool = True) -> list[dict]:
    """The blind judges of a text, each as the analysis spec it reads with.

    They read with the chapter-analysis rubric. The judges of an adaptation, and of a pilot
    of one, are told to rate the wording alone (``wording``); the judges of an original read
    by the whole rubric. With no seats configured the judge is the chapter-analysis model.
    """

    base = analysis_spec(language)
    if wording:
        base = {
            **base,
            "prompt_version": (
                WORDING_PROMPT_VERSION if language == "en" else LOCALIZED_WORDING_PROMPT_VERSION
            ),
            "system_prompt": base["system_prompt"] + WORDING_NOTE,
        }
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


def judge_readings(*, wording: bool = True) -> int:
    """How often each judge reads a text.

    A judge's single reading wavers at a level's boundary, and every chapter of an adaptation
    has to hold its level, so its judges read ``DIFFICULTY_READINGS`` times. An original's
    level is a label drawn from all its chapters, where a wavering reading is one vote among
    thirty: its judges read once.
    """

    return max(1, settings.DIFFICULTY_READINGS) if settings.DIFFICULTY_JUDGES and wording else 1


def agreed(verdicts: list[dict]) -> bool:
    """Whether more than one judge read the text and all of them at the same level."""

    return len(verdicts) > 1 and len({verdict["max_level"] for verdict in verdicts}) == 1


def panel_readings(read, specs: list[dict], readings: int, standing=None) -> list[dict]:
    """Each judge's verdict on a text, read no more often than the judges need to agree.

    Every judge reads once. Where their first readings give the same level that is the
    verdict; only where they differ does each read ``readings`` times and its middle reading
    count. Of 48 texts both judges read three times, their first readings agreed on 37, one
    judge never gave two different levels, and stopping at an agreeing first reading would
    have changed one verdict, by a level the adaptation gate already allows a disputed
    chapter. ``read(spec, count)`` reads; ``standing(count)`` gives the verdicts already
    made with ``count`` readings, None where a judge has made none.
    """

    def verdicts(count: int) -> list[dict]:
        have = standing(count) if standing else [None] * len(specs)
        return [made or read(spec, count) for spec, made in zip(specs, have, strict=True)]

    full = standing(readings) if standing else None
    if full and all(full):
        return full
    if readings > 1 and len(specs) > 1:
        first = verdicts(1)
        if agreed(first):
            return first
    return verdicts(readings)


def decisive_runs(verdicts: list[dict]) -> list[str]:
    """The readings that stand for a chapter: the strictest judge's, one AI run per window.

    A judge's verdict lists every run it made, reading by reading; the reading that stands is
    the first whose highest window is the judge's level, as ``judge_text`` kept it.
    """

    decisive = max(verdicts, key=lambda verdict: LEVELS.index(verdict["max_level"]))
    windows = len(decisive["windows"])
    reading = decisive.get("readings", [decisive["max_level"]]).index(decisive["max_level"])
    return decisive["ai_run_ids"][reading * windows : (reading + 1) * windows]


def judge_label(language: str) -> str:
    """The judges by name, as an assessment and a probe record who judged."""

    return " + ".join(spec["model"] for spec in judge_specs(language))


def _middle(levels: list[str]) -> str:
    """The middle reading; of an even number, the higher of the two in the middle."""

    return sorted(levels, key=LEVELS.index)[len(levels) // 2]


def _read(run, window, spec, configuration, prompt, provider, reader_facing=False) -> AIRun:
    """One reading of one window. A rejected answer is asked for once more.

    A judge is rejected when it cites words that are not in the text. A panel makes many
    calls for one pilot, and one bad answer should cost a call, not the whole assessment.
    """

    try:
        return _attempt(
            run, window, spec, configuration, prompt, provider, reader_facing=reader_facing
        )
    except CitationRejected:
        # only a bad citation is asked for again here; a broken call was already tried twice
        # on its way up, and a used-up allowance would refuse the same way
        return _attempt(
            run, window, spec, configuration, prompt, provider, reader_facing=reader_facing
        )


def windows_of(blocks: list[dict], window_bytes: int) -> list[list[dict]]:
    """The blocks in the windows a judge reads them in."""

    parts, current = [], []
    for block in blocks:
        if len(_json([block]).encode()) > window_bytes:
            raise ValueError("A block exceeds the judge window limit.")
        if current and len(_json([*current, block]).encode()) > window_bytes:
            parts.append(current)
            current = []
        current.append(block)
    if current:
        parts.append(current)
    return parts


def judge_text(
    *,
    edition,
    key: str,
    seed,
    summary: dict,
    chapter_sequence: int,
    blocks: list[dict],
    spec: dict,
    readings: int,
    provider,
    processor_version: str = "pilot-difficulty-v1",
    reader_facing: bool = False,
) -> dict:
    """One judge's assessment of a text: every window read ``readings`` times.

    ``key`` and ``seed`` name what is judged, a pilot or a chapter of an edition; the run is
    kept under the edition, and a text already judged by this judge is not read again.
    ``reader_facing`` holds the judge's prose to the edition's language: a chapter's
    description and recap are shown to readers, a pilot's are not.
    """

    parts = windows_of(blocks, spec["window_bytes"])
    if not parts:
        raise ValueError("No text to assess.")
    plan = snapshot(edition, spec)
    asked = spec_identity(spec)
    # A single reading keeps the identity past assessments were saved under.
    first = _hash([seed, asked, blocks])
    identity = first if readings == 1 else _hash([seed, asked, blocks, readings])
    # readings made while prices were part of the identity stand, at the prices of their day
    legacy = _hash([seed, spec, blocks]) if readings == 1 else _hash([seed, spec, blocks, readings])
    standing = PipelineRun.objects.filter(
        idempotency_key=f"{key}:{legacy}", status=PipelineRun.Status.SUCCEEDED
    ).first()
    if standing is not None:
        return standing.summary["assessment"]
    run, _ = PipelineRun.objects.get_or_create(
        idempotency_key=f"{key}:{identity}",
        defaults={
            "edition": edition,
            "stage": PipelineRun.Stage.ADAPT,
            "processor_version": processor_version,
            "input_hash": plan["hash"],
            "summary": {**summary, "spec": spec},
        },
    )
    if run.status == PipelineRun.Status.SUCCEEDED:
        return run.summary["assessment"]
    # A run that failed or was cancelled starts again against the edition as it stands now:
    # other chapters may have changed since, and its text is the same or it would not be found.
    # So does one left running by a worker that died: nothing has touched it for longer than
    # a reading takes.
    abandoned = Q(status=PipelineRun.Status.RUNNING, updated_at__lt=timezone.now() - ABANDONED)
    if not PipelineRun.objects.filter(
        Q(status__in=[PipelineRun.Status.QUEUED, PipelineRun.Status.FAILED]) | abandoned,
        pk=run.id,
    ).update(
        status=PipelineRun.Status.RUNNING,
        started_at=timezone.now(),
        updated_at=timezone.now(),
        error="",
        input_hash=plan["hash"],
    ):
        raise ValueError("Assessment already running; inspect its ledger before retrying.")
    run.refresh_from_db()
    try:
        configuration, prompt = _configuration(spec)
        if provider is None and spec["provider"] != "openai":
            provider = provider_for(spec["provider"], spec["model"])
        taken = []
        for reading in range(1, readings + 1):
            results = []
            for index, part in enumerate(parts, 1):
                data = {
                    "language": edition.language,
                    "chapter_sequence": chapter_sequence,
                    "window": index,
                    "window_count": len(parts),
                    "partial": len(parts) > 1,
                    "blocks": part,
                }
                # A later reading is a new call, not the first one's cached answer. The first
                # is the judge's single reading of this text where it has made one: a judge
                # asked to read three times after disagreeing reads twice more.
                key = [first, data] if reading == 1 else [identity, data, reading]
                window = {"hash": _hash(key), "data": data}
                results.append(
                    _read(run, window, spec, configuration, prompt, provider, reader_facing)
                )
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
    except Exception as error:
        PipelineRun.objects.filter(pk=run.id).update(
            status=PipelineRun.Status.FAILED,
            finished_at=timezone.now(),
            error=(
                str(error)[:1000]
                if isinstance(error, (AllowanceUsedUp, NetworkDown))
                else "Pilot assessment failed; inspect AI ledger."
            ),
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
    # No target, author, work title, generation prompt or judge's previous answer is supplied,
    # and the protected verse is left out, as it is from an adaptation's chapters.
    blocks = judged_blocks(
        [
            {"block_id": b["block_id"], "type": b["type"], "text": adapted[b["block_id"]]["text"]}
            for b in source["blocks"]
            if adapted[b["block_id"]]["text"].strip()
        ],
        adaptation=True,
    )
    if not blocks:
        raise ValueError("No pilot text to assess.")
    readings = judge_readings()
    verdicts = panel_readings(
        lambda spec, count: judge_text(
            edition=pilot.edition,
            key=f"{pilot.id}:pilot-difficulty",
            seed=generation.input_hash,
            summary={"pilot_id": str(pilot.id)},
            chapter_sequence=chapter.sequence,
            blocks=blocks,
            spec=spec,
            readings=count,
            provider=provider,
        ),
        specs,
        readings,
    )
    assessment = panel_verdict(verdicts, pilot.edition.language, readings)
    pilot.summary = {**pilot.summary, "difficulty_check": assessment}
    pilot.save(update_fields=["summary", "updated_at"])
    return assessment


def panel_verdict(verdicts: list[dict], language: str, readings: int) -> dict:
    """The panel's assessment: the strictest judge decides, and its windows are the evidence."""

    decisive = max(verdicts, key=lambda verdict: LEVELS.index(verdict["max_level"]))
    return {
        "prompt_version": decisive["prompt_version"],
        "model": judge_label(language),
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
