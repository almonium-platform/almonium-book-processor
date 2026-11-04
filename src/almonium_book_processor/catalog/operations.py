"""What the pipeline has done and is doing, one line per thing, newest first.

Two sources share the list: the steps a production logs ("The probe is running.") and every
AI call in the ledger. A call with no end is simply a line that is still running. A call whose
worker died has no end either, so a line counts as running only while its job is open and it
is younger than the longest a call can take.

Everything is read from the ledger and the productions' logs, and nothing here calls a model.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from decimal import Decimal

from django.conf import settings
from django.contrib.admin.views.decorators import staff_member_required
from django.db.models import Count, Max, Q, Sum
from django.db.models.fields.json import KeyTextTransform, KeyTransform
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from almonium_book_processor.ai.pricing import PLAN_WEEK_USD
from almonium_book_processor.catalog.activity import ACTIVE_STATUSES, _fingerprint
from almonium_book_processor.catalog.models import AIRun, PipelineRun, PlanAccount

PAGE = 200
FILTERS = {
    "": "Everything",
    "live": "Running now",
    "steps": "Book steps",
    "claude-code": "Claude",
    "codex": "Codex",
}
PLAN_NAMES = {"claude-code": "Claude", "codex": "Codex"}
MODEL_NAMES = {
    "claude-opus-5-5": "Opus",
    "claude-sonnet-5-5": "Sonnet",
    "claude-fable-5-1": "Fable",
    "gpt-6-astra": "Astra",
    "gpt-6.1-sol": "Sol",
    "gpt-6-sol": "Sol",
}
PROMPT_NAMES = {
    "literary-fidelity-editor": "Audit fidelity",
    "literary-fidelity-second-opinion": "Second opinion on an audit",
    "literary-b1-adaptation-pilot": "Write B1 text",
    "literary-b2-adaptation-pilot": "Write B2 text",
    "literary-adaptation-spot-fix": "Fix a passage",
    "literary-block-translation": "Translate",
    "literary-translation-reviewer": "Review a translation",
    "literary-translation-second-opinion": "Second opinion on a translation",
    "literary-translation-adjudication": "Settle a translation finding",
    "literary-translation-final-wording": "Word a translation correction",
    "literary-chapter-summary": "Summarise a chapter",
    "literary-title-page": "Translate the title page",
    "private-import-metadata": "Read an import's metadata",
    "contextual-glosses": "Write notes",
    "modernisation-edition-advice": "Advise on modernising",
}
PROGRESS = re.compile(r"\s*\(\d+%\)")


def _longest_call() -> timedelta:
    """A CLI call is tried twice, each up to its timeout."""

    seconds = max(settings.CLAUDE_CODE_TIMEOUT_SECONDS, settings.CODEX_TIMEOUT_SECONDS)
    return timedelta(seconds=2 * seconds + 300)


def _running_filter(now: datetime) -> Q:
    return Q(
        finished_at__isnull=True,
        status__in=(AIRun.Status.QUEUED, AIRun.Status.SUBMITTED),
        created_at__gte=now - _longest_call(),
    ) & (Q(pipeline_run__isnull=True) | Q(pipeline_run__status__in=ACTIVE_STATUSES))


def _operation(prompt: str, stage: str | None) -> str:
    if prompt == "chapter-analysis":
        return "Grade a source chapter" if stage == "chapter_analysis" else "Judge difficulty"
    return PROMPT_NAMES.get(prompt) or prompt.replace("-", " ").capitalize()


def _account_names() -> dict[tuple[str, str], str]:
    """The name before the @ where the account's email is known, else its directory."""

    return {
        (provider, account): (email or account).split("@")[0]
        for provider, account, email in PlanAccount.objects.values_list(
            "provider", "account", "email"
        )
    }


def _duration(seconds: float) -> str:
    seconds = max(0, int(seconds))
    if seconds < 60:
        return f"{seconds}s"
    minutes, seconds = divmod(seconds, 60)
    if minutes < 60:
        return f"{minutes}m {seconds:02d}s"
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h {minutes:02d}m"


def _week_share(provider: str, cost: Decimal) -> Decimal | None:
    week = PLAN_WEEK_USD.get(provider)
    return None if week is None else cost / week * 100


def _share_text(share: Decimal) -> str:
    return "<0.01%" if share < Decimal("0.01") else f"{share:.2f}%"


def _used(provider: str, cost: Decimal | None) -> tuple[str, str]:
    """What a call used, as the line shows it and as its tooltip explains it."""

    if not cost:
        return "", ""
    share = _week_share(provider, cost)
    if share is None:
        return f"${cost:.4f}", "Estimated price on the metered API."
    week = PLAN_WEEK_USD[provider]
    return (
        _share_text(share),
        f"About ${cost:.3f} of the plan's ${week:.2f} week. An estimate from the call's tokens, "
        "not a reading of the meter.",
    )


def _calls(now: datetime, *, chosen: str, work: str, before: datetime | None) -> list[dict]:
    runs = AIRun.objects.order_by("-created_at")
    if chosen == "live":
        runs = runs.filter(_running_filter(now))
    elif chosen in PLAN_NAMES:
        runs = runs.filter(model_configuration__provider=chosen)
    if work:
        runs = runs.filter(edition__work_id=work)
    if before:
        runs = runs.filter(created_at__lt=before)
    return list(
        runs.annotate(
            chapter=KeyTextTransform("chapter_title", "pipeline_run__summary"),
            level=KeyTextTransform("target_level", "pipeline_run__summary"),
            pilot=KeyTextTransform("pilot_id", "pipeline_run__summary"),
        ).values(
            "created_at",
            "started_at",
            "finished_at",
            "status",
            "error",
            "estimated_cost_usd",
            "plan_account",
            "edition_id",
            "edition__title",
            "edition__work_id",
            "tombstone__title",
            "model_configuration__provider",
            "model_configuration__model",
            "prompt_template__name",
            "pipeline_run__stage",
            "pipeline_run__status",
            "chapter",
            "level",
            "pilot",
        )[: PAGE + 1]
    )


def _call_lines(rows: list[dict], now: datetime) -> list[dict]:
    accounts = _account_names()
    # A judge's or an auditor's job names the pilot it reads; the chapter is the pilot's.
    pilots = {
        str(row["id"]): row
        for row in PipelineRun.objects.filter(
            id__in={row["pilot"] for row in rows if row["pilot"] and not row["chapter"]}
        )
        .annotate(
            chapter=KeyTextTransform("chapter_title", "summary"),
            level=KeyTextTransform("target_level", "summary"),
        )
        .values("id", "chapter", "level")
    }
    longest = _longest_call()
    lines = []
    for row in rows:
        provider = row["model_configuration__provider"]
        pilot = pilots.get(row["pilot"] or "") or {}
        open_job = row["pipeline_run__status"] in (*ACTIVE_STATUSES, None)
        running = (
            row["finished_at"] is None
            and row["status"] in (AIRun.Status.QUEUED, AIRun.Status.SUBMITTED)
            and open_job
            and now - row["created_at"] < longest
        )
        begun = row["started_at"] or row["created_at"]
        used, used_note = _used(provider, row["estimated_cost_usd"])
        account = row["plan_account"]
        lines.append(
            {
                "kind": "call",
                "at": row["created_at"],
                "book": row["edition__title"] or row["tombstone__title"] or "Removed book",
                "edition_id": row["edition_id"],
                "work_id": row["edition__work_id"],
                "level": row["level"] or pilot.get("level") or "",
                "chapter": row["chapter"] or pilot.get("chapter") or "",
                "text": _operation(row["prompt_template__name"], row["pipeline_run__stage"]),
                "plan": PLAN_NAMES.get(provider, provider),
                "provider": provider,
                "model": MODEL_NAMES.get(
                    row["model_configuration__model"], row["model_configuration__model"]
                ),
                "account": accounts.get((provider, account), account) if account else "",
                "running": running,
                "ended": row["finished_at"] is not None,
                "failed": row["status"] == AIRun.Status.FAILED,
                "error": row["error"][:200],
                "took": _duration(((row["finished_at"] or now) - begun).total_seconds()),
                "used": used,
                "used_note": used_note,
            }
        )
    return lines


def _step_lines(
    since: datetime | None, until: datetime | None, *, work: str, chosen: str
) -> list[dict]:
    """The productions' own logs, a step's progress notes folded into its first line."""

    productions = PipelineRun.objects.filter(
        processor_version="production-v1", summary__has_key="log"
    )
    if since:
        productions = productions.filter(updated_at__gte=since)
    if work:
        productions = productions.filter(edition__work_id=work)
    if chosen == "steps":
        # no call sets the page's window here: a page of steps is the newest productions
        productions = productions.order_by("-updated_at")[: PAGE // 4]
    lines = []
    for production in productions.annotate(log=KeyTransform("log", "summary")).values(
        "edition_id", "edition__title", "edition__work_id", "log"
    ):
        said: dict[tuple, str] = {}
        for entry in production["log"] or []:
            note = PROGRESS.sub("", entry["note"])
            key = (entry["level"], entry["step"])
            if said.get(key) == note:
                continue
            said[key] = note
            at = parse_datetime(entry["at"])
            if (since and at < since) or (until and at >= until):
                continue
            lines.append(
                {
                    "kind": "step",
                    "at": at,
                    "book": production["edition__title"],
                    "edition_id": production["edition_id"],
                    "work_id": production["edition__work_id"],
                    "level": entry["level"],
                    "text": note,
                }
            )
    return lines


def _with_days(lines: list[dict]) -> list[dict]:
    day = None
    for line in lines:
        local = timezone.localtime(line["at"]).date()
        line["new_day"] = local if local != day else None
        day = local
    return lines


def _last_hour(now: datetime) -> list[dict]:
    rows = (
        AIRun.objects.filter(created_at__gte=now - timedelta(hours=1))
        .values("model_configuration__provider")
        .annotate(calls=Count("id"), cost=Sum("estimated_cost_usd"))
        .order_by("model_configuration__provider")
    )
    hour = []
    for row in rows:
        provider = row["model_configuration__provider"]
        share = _week_share(provider, row["cost"] or Decimal(0))
        if share is not None:
            hour.append(
                {
                    "plan": PLAN_NAMES[provider],
                    "calls": row["calls"],
                    "share": _share_text(share),
                }
            )
    return hour


def operations_activity() -> dict:
    now = timezone.now()
    recent = AIRun.objects.filter(created_at__gte=now - timedelta(hours=2)).aggregate(
        calls=Count("id"), latest=Max("updated_at")
    )
    steps = PipelineRun.objects.filter(
        processor_version="production-v1", status__in=ACTIVE_STATUSES
    ).aggregate(latest=Max("updated_at"))
    running = AIRun.objects.filter(_running_filter(now)).count()
    return {
        "fingerprint": _fingerprint([(recent["calls"], recent["latest"], steps["latest"])]),
        "active": [{"running": running}] if running else [],
    }


def _before(request: HttpRequest) -> datetime | None:
    value = request.GET.get("before") or ""
    try:
        return parse_datetime(value)
    except ValueError:
        return None


@staff_member_required
def operations_view(request: HttpRequest) -> HttpResponse:
    now = timezone.now()
    chosen = request.GET.get("show", "")
    chosen = chosen if chosen in FILTERS else ""
    work = request.GET.get("book", "")
    if not re.fullmatch(r"[0-9a-fA-F-]{36}", work):
        work = ""
    before = _before(request)

    rows = [] if chosen == "steps" else _calls(now, chosen=chosen, work=work, before=before)
    more = len(rows) > PAGE
    rows = rows[:PAGE]
    lines = _call_lines(rows, now)
    # steps fill the same stretch of time as the calls on the page
    oldest = rows[-1]["created_at"] if more else None
    if chosen in ("", "steps"):
        lines += _step_lines(oldest, before, work=work, chosen=chosen)
    lines.sort(key=lambda line: line["at"], reverse=True)
    if chosen == "steps":
        more = len(lines) > PAGE
        lines = lines[:PAGE]
        oldest = lines[-1]["at"] if more else None

    book = next(
        (line["book"] for line in lines if line["work_id"] and str(line["work_id"]) == work), ""
    )
    activity = operations_activity()
    return render(
        request,
        "catalog/operations.html",
        {
            "lines": _with_days(lines),
            "filters": [
                {"key": key, "label": label, "on": key == chosen} for key, label in FILTERS.items()
            ],
            "chosen": chosen,
            "work": work,
            "book": book,
            "older": oldest.isoformat() if oldest else "",
            "running": AIRun.objects.filter(_running_filter(now)).count(),
            "last_hour": _last_hour(now),
            # an older page stands still: only the newest lines move
            "live_url": "" if before else reverse("catalog:operations-activity"),
            "fingerprint": activity["fingerprint"],
        },
    )


@staff_member_required
def operations_activity_view(request: HttpRequest) -> JsonResponse:  # noqa: ARG001
    return JsonResponse(operations_activity())
