"""Where money went twice: the ledger read for waste, so nobody has to watch sixty books.

The pipeline runs where network calls fail, plan sessions hit their limits and workers are
restarted, and the owner cannot follow dozens of books through it. Every paid unit is meant
to be bought once; this reads the AI run ledger and the catalogue for the ways that has
gone wrong before (24 October 2026: identical requests paid again, a book written twice,
a window re-asked on every tick, a paid write purged) and reports them as numbers.

An identical request is the same payload to the same model under the same input hash. The
judges deliberately read a disputed chapter three times with the same payload; those
readings carry different input hashes and are not counted.
"""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from datetime import timedelta
from decimal import Decimal

from django.utils import timezone

from almonium_book_processor.catalog.models import (
    AIRun,
    Edition,
    EditionTombstone,
    SpendGuardReport,
)

WINDOW = timedelta(hours=24)
# a window asked more often than this with the same failure is asked on every tick
REASKED_AFTER = 2


def _payload_hash(payload: dict) -> str:
    return hashlib.sha1(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()


def guard_report(*, window: timedelta = WINDOW) -> dict:
    """The numbers, and what is behind them, without any book text."""

    since = timezone.now() - window
    groups: dict[tuple, list] = defaultdict(list)
    checked = 0
    runs = (
        AIRun.objects.exclude(request_payload={})
        .select_related("pipeline_run", "model_configuration")
        .only(
            "id",
            "request_payload",
            "input_hash",
            "status",
            "estimated_cost_usd",
            "created_at",
            "model_configuration__name",
            "model_configuration__id",
            "pipeline_run__stage",
            "pipeline_run__processor_version",
        )
        .order_by("created_at")
    )
    for run in runs.iterator(chunk_size=500):
        checked += 1
        key = (_payload_hash(run.request_payload), run.model_configuration_id, run.input_hash)
        groups[key].append(run)

    duplicates = []
    new_calls, new_usd, total_calls, total_usd = 0, Decimal("0"), 0, Decimal("0")
    reasked = []
    for rows in groups.values():
        if len(rows) < 2:
            continue
        extras = rows[1:]
        cost = sum((r.estimated_cost_usd or Decimal("0")) for r in extras)
        recent = [r for r in extras if r.created_at >= since]
        total_calls += len(extras)
        total_usd += cost
        new_calls += len(recent)
        new_usd += sum((r.estimated_cost_usd or Decimal("0")) for r in recent)
        first = rows[0]
        where = first.pipeline_run
        entry = {
            "model": str(first.model_configuration.name)[:60],
            "stage": where.stage if where else "",
            "version": where.processor_version if where else "",
            "calls": len(rows),
            "extra_usd": str(cost.quantize(Decimal("0.0001"))),
            "statuses": sorted({r.status for r in rows}),
            "last_at": rows[-1].created_at.isoformat(),
        }
        duplicates.append(entry)
        if len(rows) > REASKED_AFTER and all(r.status == AIRun.Status.FAILED for r in rows):
            reasked.append(entry)
    duplicates.sort(key=lambda e: Decimal(e["extra_usd"]), reverse=True)

    from almonium_book_processor.catalog.adaptation_quality import adaptation_target

    by_level: dict[tuple, list] = defaultdict(list)
    for edition in Edition.objects.filter(edition_type=Edition.EditionType.ADAPTATION).exclude(
        literary_register=Edition.LiteraryRegister.LIGHTLY_MODERNISED
    ):
        by_level[(edition.source_edition_id, adaptation_target(edition))].append(edition.slug)
    twins = [sorted(slugs) for slugs in by_level.values() if len(slugs) > 1]

    purged = []
    purged_usd = Decimal("0")
    for stone in EditionTombstone.objects.filter(created_at__gte=since).order_by("created_at"):
        cost = sum(
            (r.estimated_cost_usd or Decimal("0")) for r in AIRun.objects.filter(tombstone=stone)
        )
        if cost > 0:
            purged.append(
                {
                    "slug": stone.edition_slug,
                    "reason": stone.reason,
                    "usd": str(cost.quantize(Decimal("0.0001"))),
                }
            )
            purged_usd += cost

    return {
        "window_hours": int(window.total_seconds() // 3600),
        "checked_runs": checked,
        "new_duplicate_calls": new_calls,
        "new_duplicate_usd": str(new_usd.quantize(Decimal("0.0001"))),
        "total_duplicate_calls": total_calls,
        "total_duplicate_usd": str(total_usd.quantize(Decimal("0.0001"))),
        "duplicates": duplicates[:20],
        "reasked_windows": len(reasked),
        "reasked": reasked[:20],
        "twins": twins,
        "purged": purged,
        "purged_usd": str(purged_usd.quantize(Decimal("0.0001"))),
    }


def record_report(report: dict | None = None) -> SpendGuardReport:
    report = report or guard_report()
    return SpendGuardReport.objects.create(
        window_hours=report["window_hours"],
        checked_runs=report["checked_runs"],
        new_duplicate_calls=report["new_duplicate_calls"],
        new_duplicate_usd=Decimal(report["new_duplicate_usd"]),
        total_duplicate_calls=report["total_duplicate_calls"],
        total_duplicate_usd=Decimal(report["total_duplicate_usd"]),
        twin_editions=len(report["twins"]),
        reasked_windows=report["reasked_windows"],
        purged_usd=Decimal(report["purged_usd"]),
        report=report,
    )


def latest_report() -> SpendGuardReport | None:
    return SpendGuardReport.objects.order_by("-created_at").first()


def summary_line(report: SpendGuardReport) -> str:
    """One line for the dashboard: what was paid twice in the window, and what stands."""

    parts = [
        f"{report.new_duplicate_calls} call(s) paid twice (${report.new_duplicate_usd:.2f})"
        f" in {report.window_hours} h",
        f"{report.twin_editions} twin edition(s)",
        f"{report.reasked_windows} window(s) re-asked",
    ]
    if report.purged_usd > 0:
        parts.append(f"${report.purged_usd:.2f} of paid text purged")
    return " · ".join(parts)
