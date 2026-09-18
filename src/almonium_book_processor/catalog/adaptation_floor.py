"""The adaptation floor: found one rung at a time from evidence, never typed in.

A book starts at its original level. Each rung below is tried first as a
probe: pilots on a fixed sample of chapters, each judged blind for difficulty
and audited for fidelity. A passed probe is a green light to spend on the
full edition; a failed probe closes the ladder there. What the work records
as ``adapts_to`` comes only from editions that passed both gates, with the
run ids that justify it, and a rung is retried only under a new generation,
judge or audit version, never by rolling the same judge until it passes.
"""

from __future__ import annotations

from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from almonium_book_processor.ai.adaptation import pilot_prompt
from almonium_book_processor.catalog.adaptation import (
    B1_VERSION,
    MAX_BLOCKS,
    MAX_CHARS,
    VERSION,
    digest,
    queue_pilot,
    run_pilot,
    source_snapshot,
)
from almonium_book_processor.catalog.adaptation_quality import adaptation_quality, adaptation_target
from almonium_book_processor.catalog.chapter_analysis import analysis_context, analysis_spec
from almonium_book_processor.catalog.chapter_projections import LEVELS
from almonium_book_processor.catalog.fidelity_audit import (
    SEVERITIES,
    audit_context,
    audit_pilot,
    audit_spec,
    fidelity_gate,
)
from almonium_book_processor.catalog.models import Chapter, Edition, PipelineRun, Work
from almonium_book_processor.catalog.pilot_difficulty import assess_pilot

PROBE_VERSION = "floor-probe-v1"
# Highest first; each has a pilot prompt. A2 has never been tested and is not a rung.
PROBE_LEVELS = ("B2", "B1")
SAMPLE_SIZE = 3


def probe_spec(target_level: str, language: str) -> dict:
    """Everything a verdict depends on; a change here is a new probe, not a retry."""

    prompt_version, system_prompt = pilot_prompt(target_level, language)
    judge = analysis_spec(language)
    audit = audit_spec()
    return {
        "target_level": target_level,
        "generation_processor": B1_VERSION if target_level == "B1" else VERSION,
        "generation_model": settings.OPENAI_TRANSLATION_QUALITY_MODEL,
        "generation_prompt_version": prompt_version,
        "generation_prompt_hash": digest(system_prompt),
        "judge_model": judge["model"],
        "judge_prompt_version": judge["prompt_version"],
        "audit_model": audit["model"],
        "audit_prompt_version": audit["prompt_version"],
    }


def probe_sample(edition: Edition) -> list[Chapter]:
    """First, middle and last substantive chapters that fit the pilot limits."""

    def fits(chapter: Chapter) -> bool:
        blocks = list(chapter.blocks.all())
        return (
            any(b.text.strip() for b in blocks)
            and len(blocks) <= MAX_BLOCKS
            and sum(len(b.text) for b in blocks) <= MAX_CHARS
        )

    chapters = [
        c for c in edition.chapters.order_by("sequence").prefetch_related("blocks") if fits(c)
    ]
    body = [c for c in chapters if c.analysis_role == Chapter.AnalysisRole.BODY]
    pool = body or chapters
    if not pool:
        raise ValueError("No chapter fits the pilot limits; split long chapters first.")
    if len(pool) <= SAMPLE_SIZE:
        return pool
    return [pool[0], pool[len(pool) // 2], pool[-1]]


@transaction.atomic
def queue_probe(source_id, target_level: str, *, dispatch: bool = True) -> PipelineRun:
    from almonium_book_processor.catalog.tasks import run_floor_probe

    if not settings.OPENAI_API_KEY:
        raise ValueError("Configure an OpenAI key to probe a level.")
    if target_level not in PROBE_LEVELS:
        raise ValueError("Choose B2 or B1 for a floor probe.")
    source = Edition.objects.select_for_update().select_related("work").get(pk=source_id)
    if source.work.visibility != Work.Visibility.PUBLIC:
        raise ValueError("Floor probes support public catalogue sources only.")
    if source.edition_type == Edition.EditionType.ADAPTATION:
        raise ValueError("Probe from the original edition, not from an adaptation.")
    active = source.pipeline_runs.filter(
        processor_version=PROBE_VERSION,
        summary__target_level=target_level,
        status__in=[PipelineRun.Status.QUEUED, PipelineRun.Status.RUNNING],
    ).first()
    if active is not None:
        return active
    rows = ladder(source)
    row = next((r for r in rows if r["level"] == target_level), None)
    if row is None:
        raise ValueError(f"{target_level} is not below this book's level.")
    if not row["can_probe"]:
        raise ValueError(f"{target_level}: {row['note']}")
    spec = probe_spec(target_level, source.language)
    sample = probe_sample(source)
    input_hash = digest(
        [spec, [digest(source_snapshot(c, target_level=target_level)) for c in sample]]
    )
    run, created = PipelineRun.objects.get_or_create(
        idempotency_key=f"{source.id}:floor-probe:{target_level.lower()}:{input_hash}",
        defaults={
            "edition": source,
            "stage": PipelineRun.Stage.ADAPT,
            "processor_version": PROBE_VERSION,
            "input_hash": input_hash,
            "summary": {
                "target_level": target_level,
                "spec": spec,
                "chapters": [
                    {"id": str(c.id), "sequence": c.sequence, "title": c.title} for c in sample
                ],
                "results": [],
                "verdict": None,
            },
        },
    )
    if not created and run.status in (PipelineRun.Status.SUCCEEDED, PipelineRun.Status.RUNNING):
        return run
    run.status = PipelineRun.Status.QUEUED
    run.error = ""
    run.finished_at = None
    run.save(update_fields=["status", "error", "finished_at", "updated_at"])
    if dispatch:
        transaction.on_commit(lambda: run_floor_probe.delay(str(run.id)))
    return run


def run_probe(run_id, *, provider=None, judge=None, auditor=None) -> None:
    if not PipelineRun.objects.filter(pk=run_id, status=PipelineRun.Status.QUEUED).update(
        status=PipelineRun.Status.RUNNING, started_at=timezone.now(), progress=1
    ):
        return
    run = PipelineRun.objects.select_related("edition__work").get(pk=run_id)
    source = run.edition
    level = run.summary["target_level"]
    try:
        if probe_spec(level, source.language) != run.summary["spec"]:
            raise ValueError("Generation, judge or audit configuration changed; queue a new probe.")
        results = []
        for entry in run.summary["chapters"]:
            title = entry["title"] or f"chapter {entry['sequence']}"
            chapter = source.chapters.get(pk=entry["id"])
            pilot = queue_pilot(source.id, chapter.id, target_level=level, dispatch=False)
            if pilot.status == PipelineRun.Status.QUEUED:
                try:
                    run_pilot(pilot.id, provider=provider)
                except Exception as error:
                    detail = str(error) if isinstance(error, ValueError) else type(error).__name__
                    raise ValueError(f"{title}: generation failed. {detail}") from error
            pilot.refresh_from_db()
            if pilot.status != PipelineRun.Status.SUCCEEDED:
                raise ValueError(f"{title}: generation {pilot.status}. {pilot.error}".strip())
            assessment = assess_pilot(pilot.id, provider=judge)
            review = audit_pilot(pilot.id, provider=auditor)
            judged = assessment["max_level"]
            results.append(
                {
                    "chapter_id": entry["id"],
                    "sequence": entry["sequence"],
                    "title": entry["title"],
                    "pilot_id": str(pilot.id),
                    "judge_estimate": assessment["cefr_estimate"],
                    "judge_max_level": judged,
                    "difficulty_ok": LEVELS.index(judged) <= LEVELS.index(level),
                    "material": review["counts"]["material"],
                    "minor": review["counts"]["minor"],
                    "uncertain": review["counts"]["uncertain"],
                    "fidelity_ok": review["counts"]["material"] == 0,
                    "cost_usd": str(
                        (pilot.ai_runs.get(pk=pilot.summary["ai_run_id"]).estimated_cost_usd or 0)
                        + Decimal(assessment["cost_usd"])
                        + Decimal(review["cost_usd"])
                    ),
                }
            )
            run.summary = {**run.summary, "results": results}
            run.progress = int(95 * len(results) / len(run.summary["chapters"]))
            run.save(update_fields=["summary", "progress", "updated_at"])

        reasons = _probe_reasons(results)
        run.summary = {
            **run.summary,
            "results": results,
            "verdict": "failed" if reasons else "passed",
            "reasons": reasons,
            "cost_usd": str(sum(Decimal(r["cost_usd"]) for r in results)),
        }
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
    refresh_adaptation_floor(source.work)


def judge_standalone_pilot(pilot_id, *, judge=None, auditor=None) -> None:
    """After a staff pilot generates, judge and audit it without being asked."""

    pilot = PipelineRun.objects.get(pk=pilot_id)
    if pilot.status != PipelineRun.Status.SUCCEEDED or pilot.summary.get(
        "source_edition_id"
    ) != str(pilot.edition_id):
        return
    assess_pilot(pilot.id, provider=judge)
    audit_pilot(pilot.id, provider=auditor)


# ---------------------------------------------------------------------------
# What a level's evidence says, and the floor that follows from it.


def edition_gates(edition: Edition) -> dict:
    """Both gates for one adaptation, as they stand for its current text."""

    target = adaptation_target(edition)
    analysis = analysis_context(edition)
    quality = adaptation_quality(edition, analysis)
    difficulty_ok = bool(target) and not quality.get("adaptation_blocker")
    fidelity_ok, audit = fidelity_gate(edition)
    audit_state = audit_context(edition)
    return {
        "level": target,
        "difficulty_ok": difficulty_ok,
        "difficulty_note": quality.get("adaptation_blocker") or "",
        "difficulty_run": analysis.get("chapter_analysis_run"),
        "fidelity_ok": fidelity_ok,
        "fidelity_state": audit_state["fidelity_audit_state"],
        "fidelity_open_findings": audit_state["fidelity_open_findings"],
        "fidelity_run": audit,
        "reached": bool(target) and difficulty_ok and fidelity_ok,
    }


def edition_reached(edition: Edition) -> dict | None:
    if edition.withdrawal_requested_at or not edition.blocks.exists():
        return None
    gates = edition_gates(edition)
    if not gates["reached"]:
        return None
    return {
        "state": "reached",
        "level": gates["level"],
        "edition_id": str(edition.id),
        "edition_slug": edition.slug,
        "edition_status": edition.status,
        "difficulty_run_id": str(gates["difficulty_run"].id),
        "fidelity_run_id": str(gates["fidelity_run"].id),
    }


def refresh_adaptation_floor(work: Work) -> Work:
    """Recompute ``adapts_to`` from the editions and probes that exist right now."""

    work = Work.objects.filter(pk=work.pk).first()
    if work is None:
        return work
    if work.editions.filter(promoted_from__gt="").exists():
        # The floor arrived in the bundle with the evidence that produced it;
        # this environment has no judge or audit ledger to recompute it from.
        return work
    levels: dict[str, dict] = {}
    for edition in work.editions.filter(edition_type=Edition.EditionType.ADAPTATION).select_related(
        "work", "source_edition"
    ):
        reached = edition_reached(edition)
        if reached is None:
            continue
        level = reached["level"]
        current = levels.get(level)
        if current is None or (
            current["edition_status"] != Edition.Status.PUBLISHED
            and edition.status == Edition.Status.PUBLISHED
        ):
            levels[level] = reached
    probes = PipelineRun.objects.filter(
        edition__work=work,
        processor_version=PROBE_VERSION,
        status=PipelineRun.Status.SUCCEEDED,
    ).order_by("created_at")
    for probe in probes:
        level = probe.summary["target_level"]
        if levels.get(level, {}).get("state") == "reached":
            continue
        levels[level] = {
            "state": f"probe_{probe.summary['verdict']}",
            "level": level,
            "probe_id": str(probe.id),
            "pilot_ids": [r["pilot_id"] for r in probe.summary.get("results", [])],
            "reasons": probe.summary.get("reasons", []),
            "spec": probe.summary["spec"],
            "recorded_at": probe.finished_at.isoformat() if probe.finished_at else None,
        }
    reached_levels = [level for level, entry in levels.items() if entry["state"] == "reached"]
    adapts_to = min(reached_levels, key=LEVELS.index) if reached_levels else None
    if work.adapts_to != adapts_to or (work.adaptation_evidence.get("levels") or {}) != levels:
        work.adapts_to = adapts_to
        work.adaptation_evidence = {"levels": levels, "computed_at": timezone.now().isoformat()}
        work.save(update_fields=["adapts_to", "adaptation_evidence", "updated_at"])
    return work


def reached_levels(work: Work) -> list[str]:
    """Levels the work has a gate-passing adaptation at, highest first."""

    return sorted(
        (
            level
            for level, entry in (work.adaptation_evidence.get("levels") or {}).items()
            if entry.get("state") == "reached"
        ),
        key=LEVELS.index,
        reverse=True,
    )


def original_level(edition: Edition, analysis: dict | None = None) -> str | None:
    if edition.cefr_level:
        return edition.cefr_level
    if analysis is None:
        analysis = analysis_context(edition)
    book = analysis.get("book_difficulty") or {}
    level = book.get("cefr_estimate")
    return level if level in LEVELS else None


def ladder(edition: Edition, analysis: dict | None = None) -> list[dict]:
    """One row per rung below the original, top down, with the single next action."""

    work = edition.work
    original = original_level(edition, analysis)
    evidence = work.adaptation_evidence.get("levels") or {}
    rows: list[dict] = []
    open_rung = True
    for level in PROBE_LEVELS:
        if original in LEVELS and LEVELS.index(level) >= LEVELS.index(original):
            continue
        record = evidence.get(level) or {}
        editions = [
            {"edition": candidate, **edition_gates(candidate)}
            for candidate in work.editions.filter(
                edition_type=Edition.EditionType.ADAPTATION,
                source_edition=edition,
                withdrawal_requested_at__isnull=True,
            ).select_related("work", "source_edition")
            if adaptation_target(candidate) == level
        ]
        probe = (
            edition.pipeline_runs.filter(
                processor_version=PROBE_VERSION, summary__target_level=level
            )
            .order_by("-created_at")
            .first()
        )
        probe_current = bool(probe) and probe.summary.get("spec") == probe_spec(
            level, edition.language
        )
        if record.get("state") == "reached" or any(e["reached"] for e in editions):
            state, note = "reached", "Both gates passed."
        elif probe and probe.status in (PipelineRun.Status.QUEUED, PipelineRun.Status.RUNNING):
            state, note = "probing", "Probe running."
        elif probe and probe.status == PipelineRun.Status.FAILED:
            state, note = "error", probe.error or "Probe did not finish."
        elif probe and probe.summary.get("verdict") == "passed":
            state, note = "probe_passed", "Probe passed; the full edition is worth generating."
        elif probe and probe.summary.get("verdict") == "failed" and probe_current:
            state, note = "probe_failed", "; ".join(probe.summary.get("reasons", []))
        elif editions:
            state, note = "generated", "Edition exists; pass its difficulty gate and audit it."
        elif probe:
            state, note = "untried", "Earlier probe ran under a superseded configuration."
        else:
            state, note = "untried", "Not tried."
        can_probe = open_rung and state in ("untried", "error")
        if not open_rung and state in ("untried", "error"):
            note = "Reach the level above first."
        rows.append(
            {
                "level": level,
                "state": state,
                "note": note,
                "record": record,
                "editions": editions,
                "probe": probe,
                "probe_current": probe_current,
                "can_probe": can_probe,
                "can_generate": state == "probe_passed" and not editions,
            }
        )
        open_rung = state in ("reached", "probe_passed")
    return rows


def ladder_context(edition: Edition, analysis: dict | None = None) -> dict:
    rows = ladder(edition, analysis)
    return {
        "adaptation_ladder": rows,
        "adaptation_original_level": original_level(edition, analysis),
        "adaptation_floor": edition.work.adapts_to,
        "adaptation_floor_found": any(r["state"] == "probe_failed" for r in rows),
        "adaptation_next_probe": next((r["level"] for r in rows if r["can_probe"]), None),
    }


# ---------------------------------------------------------------------------
# Evidence gathered before probes existed: standalone pilots that were judged
# and audited by hand-run scripts can be grouped into a probe record, as long
# as they are exactly what a probe would run today.


def backfill_probe(source: Edition, target_level: str) -> PipelineRun:
    """Record a probe from existing judged and audited pilots under the current spec."""

    from almonium_book_processor.catalog.fidelity_audit import AUDIT_VERSION
    from almonium_book_processor.catalog.fidelity_audit import PROMPT_NAME as AUDIT_PROMPT

    spec = probe_spec(target_level, source.language)
    judge = analysis_spec(source.language)
    pilots: dict[str, PipelineRun] = {}
    for pilot in source.pipeline_runs.filter(
        stage=PipelineRun.Stage.ADAPT,
        processor_version=spec["generation_processor"],
        status=PipelineRun.Status.SUCCEEDED,
        summary__target_level=target_level,
        summary__source_edition_id=str(source.id),
        summary__block_ids=None,
    ).order_by("created_at"):
        generation = pilot.ai_runs.filter(pk=pilot.summary.get("ai_run_id")).first()
        check = pilot.summary.get("difficulty_check") or {}
        if (
            generation is None
            or generation.prompt_template.version != spec["generation_prompt_version"]
            or generation.model_configuration.model != spec["generation_model"]
            or check.get("prompt_version") != judge["prompt_version"]
            or check.get("model") != judge["model"]
        ):
            continue
        pilots[pilot.summary["chapter_id"]] = pilot  # the latest matching pilot per chapter
    if not pilots:
        raise ValueError(
            f"No {target_level} pilot on this source was generated, judged and configured "
            "the way a probe would be today."
        )
    results = []
    for pilot in pilots.values():
        review = pilot.summary.get("fidelity_audit")
        if review is None:
            audit_run = source.pipeline_runs.filter(
                processor_version=AUDIT_VERSION,
                status=PipelineRun.Status.SUCCEEDED,
                summary__pilot_id=str(pilot.id),
            ).first()
            review = audit_run.summary.get("review") if audit_run else None
        if review is None:
            audit = (
                pilot.ai_runs.filter(prompt_template__name=AUDIT_PROMPT, status="succeeded")
                .order_by("-created_at")
                .first()
            )
            if audit is None:
                raise ValueError(f"Pilot {pilot.id} was never audited for fidelity.")
            issues = audit.response_payload["review"]["issues"]
            review = {
                "counts": {s: sum(i["severity"] == s for i in issues) for s in SEVERITIES},
                "cost_usd": str(audit.estimated_cost_usd or 0),
                "ai_run_ids": [str(audit.id)],
            }
        check = pilot.summary["difficulty_check"]
        chapter = source.chapters.get(pk=pilot.summary["chapter_id"])
        results.append(
            {
                "chapter_id": str(chapter.id),
                "sequence": chapter.sequence,
                "title": chapter.title,
                "pilot_id": str(pilot.id),
                "judge_estimate": check["cefr_estimate"],
                "judge_max_level": check["max_level"],
                "difficulty_ok": LEVELS.index(check["max_level"]) <= LEVELS.index(target_level),
                "material": review["counts"]["material"],
                "minor": review["counts"]["minor"],
                "uncertain": review["counts"]["uncertain"],
                "fidelity_ok": review["counts"]["material"] == 0,
                "cost_usd": str(
                    (pilot.ai_runs.get(pk=pilot.summary["ai_run_id"]).estimated_cost_usd or 0)
                    + Decimal(check["cost_usd"])
                    + Decimal(review["cost_usd"])
                ),
            }
        )
    results.sort(key=lambda r: r["sequence"])
    reasons = _probe_reasons(results)
    run, created = PipelineRun.objects.get_or_create(
        idempotency_key=(
            f"{source.id}:floor-probe:{target_level.lower()}:backfill:"
            f"{digest([spec, [r['pilot_id'] for r in results]])}"
        ),
        defaults={
            "edition": source,
            "stage": PipelineRun.Stage.ADAPT,
            "processor_version": PROBE_VERSION,
            "input_hash": digest([spec, [r["pilot_id"] for r in results]]),
            "status": PipelineRun.Status.SUCCEEDED,
            "progress": 100,
            "started_at": timezone.now(),
            "finished_at": timezone.now(),
            "summary": {
                "target_level": target_level,
                "spec": spec,
                "backfilled": True,
                "chapters": [
                    {"id": r["chapter_id"], "sequence": r["sequence"], "title": r["title"]}
                    for r in results
                ],
                "results": results,
                "verdict": "failed" if reasons else "passed",
                "reasons": reasons,
                "cost_usd": str(sum(Decimal(r["cost_usd"]) for r in results)),
            },
        },
    )
    if created:
        refresh_adaptation_floor(source.work)
    return run


def _probe_reasons(results: list[dict]) -> list[str]:
    def name(r):
        return r["title"] or f"chapter {r['sequence']}"

    reasons = [
        f"{name(r)} judged {r['judge_max_level']}" for r in results if not r["difficulty_ok"]
    ]
    reasons += [
        f"{name(r)}: {r['material']} material fidelity finding(s)"
        for r in results
        if not r["fidelity_ok"]
    ]
    return reasons
