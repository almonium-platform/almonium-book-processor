"""The Spending page: what each provider cost, by day, week or month, and what it went on.

Read from the same records the caps use (``catalog/budgets.py``): the AI run ledger for the
OpenAI API and the plans, the offline alignment runs for Modal. Money the owner pays (the
OpenAI API, Modal) and the plans' calls valued at API prices are charted apart: the plans
are an order of magnitude larger and would flatten the bills on a shared axis.

Buckets are UTC days, ISO weeks (from Monday) and calendar months, as the caps count them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from django.conf import settings
from django.db.models import Count, Sum
from django.db.models.functions import TruncDay, TruncMonth, TruncWeek
from django.utils import timezone

from almonium_book_processor.catalog import budgets
from almonium_book_processor.catalog.models import AIRun, PipelineRun
from almonium_book_processor.catalog.spend import format_usd, purpose_label
from almonium_book_processor.processing import remote_embeddings

# Fixed order, fixed colour slot: a provider keeps its colour on every chart and period.
SERIES = ("openai", "modal", "claude-code", "codex")
BILLED = ("openai", "modal")
PLANS = ("claude-code", "codex")
# How each series is named where its dollars are shown: Modal's are credits, not money.
LEGEND = {
    "openai": "OpenAI API (paid)",
    "modal": "Modal GPU (free credits)",
    "claude-code": "Claude plan",
    "codex": "Codex plan",
}
PERIODS = {
    "day": ("Days", 30, TruncDay),
    "week": ("Weeks", 12, TruncWeek),
    "month": ("Months", 12, TruncMonth),
}
ZERO = Decimal("0")
# before the first recorded call: "since" for all time (``budgets.spent`` reads None as
# this month)
EPOCH = datetime(2000, 1, 1, tzinfo=UTC)


def _floor(moment: datetime, period: str) -> datetime:
    moment = moment.astimezone(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    if period == "week":
        return moment - timedelta(days=moment.weekday())
    if period == "month":
        return moment.replace(day=1)
    return moment


def _step(start: datetime, period: str, back: int) -> datetime:
    if period == "day":
        return start - timedelta(days=back)
    if period == "week":
        return start - timedelta(weeks=back)
    month = start.month - 1 - back
    return start.replace(year=start.year + month // 12, month=month % 12 + 1)


def _label(start: datetime, period: str) -> str:
    if period == "month":
        return f"{start:%b %Y}"
    if period == "week":
        return f"{start:%-d %b}"
    return f"{start:%-d %b}"


@dataclass
class Bucket:
    start: datetime
    label: str
    values: dict[str, Decimal] = field(default_factory=lambda: dict.fromkeys(SERIES, ZERO))

    def total(self, providers=SERIES) -> Decimal:
        return sum((self.values[p] for p in providers), ZERO)

    @property
    def billed(self) -> Decimal:
        return self.total(BILLED)

    @property
    def plans(self) -> Decimal:
        return self.total(PLANS)


def _modal_runs(since: datetime | None = None):
    runs = PipelineRun.objects.filter(
        stage=PipelineRun.Stage.ALIGN, summary__embedding__modal_calls__gt=0
    )
    if since is not None:
        runs = runs.filter(updated_at__gte=since)
    for updated_at, usd, calls in runs.values_list(
        "updated_at", "summary__embedding__usd", "summary__embedding__modal_calls"
    ):
        yield updated_at, Decimal(str(usd or "0")), int(calls or 0)


def buckets(period: str, now: datetime | None = None) -> list[Bucket]:
    """The last N days, weeks or months, oldest first, every provider in each."""

    _, count, trunc = PERIODS[period]
    current = _floor(now or timezone.now(), period)
    starts = [_step(current, period, back) for back in range(count - 1, -1, -1)]
    found = {start: Bucket(start, _label(start, period)) for start in starts}
    rows = (
        AIRun.objects.filter(created_at__gte=starts[0])
        .annotate(bucket=trunc("created_at", tzinfo=UTC))
        .values("bucket", "model_configuration__provider")
        .annotate(usd=Sum("estimated_cost_usd"))
    )
    for row in rows:
        provider = row["model_configuration__provider"]
        bucket = found.get(_floor(row["bucket"], period))
        if bucket is not None and provider in bucket.values:
            bucket.values[provider] += row["usd"] or ZERO
    billed = remote_embeddings.billed_by_day(starts[0])
    if billed is not None:  # Modal's own bill, every environment together
        for day, usd in billed.items():
            moment = datetime(day.year, day.month, day.day, tzinfo=UTC)
            bucket = found.get(_floor(moment, period))
            if bucket is not None:
                bucket.values["modal"] += usd
    else:
        for updated_at, usd, _ in _modal_runs(starts[0]):
            bucket = found.get(_floor(updated_at, period))
            if bucket is not None:
                bucket.values["modal"] += usd
    return list(found.values())


def totals(now: datetime | None = None) -> list[dict]:
    """Today, this week, this month and all time, billed and plan-valued apart."""

    now = now or timezone.now()
    spans = [
        ("Today", _floor(now, "day")),
        ("This week", _floor(now, "week")),
        ("This month", _floor(now, "month")),
        ("All time", EPOCH),
    ]
    out = []
    for name, since in spans:
        values = {provider: budgets.spent(provider, since) for provider in PLANS + ("openai",)}
        values["modal"] = budgets.spent("modal", since)
        plans = values["claude-code"] + values["codex"]
        out.append(
            {
                "name": name,
                "paid": format_usd(values["openai"]),
                "credits": format_usd(values["modal"]),
                "plans": format_usd(plans),
                "of_credits": (
                    format_usd(Decimal(str(settings.MODAL_MONTHLY_CREDITS_USD)))
                    if name == "This month"
                    else ""
                ),
            }
        )
    return out


def breakdown(since: datetime) -> list[dict]:
    """What the money since ``since`` went on: provider, job and model, dearest first."""

    rows = (
        AIRun.objects.filter(created_at__gte=since)
        .values(
            "model_configuration__provider",
            "model_configuration__purpose",
            "model_configuration__model",
        )
        .annotate(
            calls=Count("id"),
            input_tokens=Sum("input_tokens"),
            output_tokens=Sum("output_tokens"),
            usd=Sum("estimated_cost_usd"),
        )
    )
    lines = [
        {
            "provider": row["model_configuration__provider"],
            "purpose": purpose_label(row["model_configuration__purpose"]),
            "model": row["model_configuration__model"],
            "calls": row["calls"],
            "tokens": f"{(row['input_tokens'] or 0) + (row['output_tokens'] or 0):,}",
            "usd": row["usd"] or ZERO,
        }
        for row in rows
    ]
    modal = list(_modal_runs(since))
    if modal:
        lines.append(
            {
                "provider": "modal",
                "purpose": "Sentence alignment embeddings",
                "model": "GPU",
                "calls": sum(calls for _, _, calls in modal),
                "tokens": None,
                "usd": budgets.spent("modal", since),
            }
        )
    for line in lines:
        name, metered = budgets.PROVIDERS.get(line["provider"], (line["provider"], True))
        line["provider_name"] = name
        line["metered"] = metered
        line["tag"] = {"modal": "credits"}.get(line["provider"], "" if metered else "valued")
        line["usd_label"] = format_usd(line["usd"])
        line["calls"] = f"{line['calls']:,}"
    return sorted(lines, key=lambda line: (not line["metered"], -line["usd"]))


# The chart ----------------------------------------------------------------------------------

WIDTH, HEIGHT = 1100, 220
LEFT, RIGHT, TOP, BOTTOM = 60, 8, 10, 26
GAP = 2  # surface gap between stacked segments
RADIUS = 4  # rounded data end, square at the baseline


def _nice_max(value: Decimal) -> Decimal:
    """The top of a four-gridline axis just above ``value``, in steps of 1, 2, 2.5 or 5."""

    if value <= 0:
        return Decimal("1")
    exponent = Decimal("0.01")
    while True:
        for base in ("1", "2", "2.5", "5"):
            step = Decimal(base) * exponent
            if value <= step * 4:
                return step * 4
        exponent *= 10


def _bar_path(x: float, y: float, width: float, height: float, rounded: bool) -> str:
    if height <= 0:
        return ""
    r = min(RADIUS, width / 2, height) if rounded else 0
    return (
        f"M{x:.1f},{y + height:.1f}V{y + r:.1f}"
        + (f"Q{x:.1f},{y:.1f} {x + r:.1f},{y:.1f}" if r else "")
        + f"H{x + width - r:.1f}"
        + (f"Q{x + width:.1f},{y:.1f} {x + width:.1f},{y + r:.1f}" if r else "")
        + f"V{y + height:.1f}Z"
    )


def chart(series: list[Bucket], providers: tuple[str, ...]) -> dict:
    """A stacked column chart of ``providers`` over the buckets, as SVG geometry."""

    peak = max((bucket.total(providers) for bucket in series), default=ZERO)
    top = _nice_max(peak)
    plot_w, plot_h = WIDTH - LEFT - RIGHT, HEIGHT - TOP - BOTTOM
    band = plot_w / max(len(series), 1)
    bar_w = min(24.0, band * 0.7)
    every = max(1, round(len(series) / 8))
    columns = []
    for index, bucket in enumerate(series):
        x = LEFT + band * index + (band - bar_w) / 2
        y = TOP + plot_h
        segments = []
        present = [p for p in providers if bucket.values[p] > 0]
        for provider in present:
            value = bucket.values[provider]
            height = float(value / top) * plot_h
            last = provider == present[-1]
            drawn = max(height - (0 if last else GAP), 0.75)
            y -= height
            segments.append(
                {
                    "provider": provider,
                    "path": _bar_path(x, y + (height - drawn), bar_w, drawn, last),
                }
            )
        columns.append(
            {
                "bucket": bucket,
                "segments": segments,
                "hit_x": round(LEFT + band * index, 1),
                "hit_w": round(band, 1),
                "label_x": round(x + bar_w / 2, 1),
                # counted from the newest, so the latest bucket is always labelled
                "show_label": (len(series) - 1 - index) % every == 0,
                "total": format_usd(bucket.total(providers)),
                "parts": [
                    (SERIES.index(p) + 1, LEGEND[p], format_usd(bucket.values[p]))
                    for p in providers
                ],
            }
        )
    ticks = [
        {"y": round(TOP + plot_h - plot_h * i / 4, 1), "label": format_usd(top * i / 4)}
        for i in range(5)
    ]
    return {
        "width": WIDTH,
        "height": HEIGHT,
        "left": LEFT,
        "right": WIDTH - RIGHT,
        "baseline": TOP + plot_h,
        "label_y": HEIGHT - 8,
        "ticks": ticks,
        "columns": columns,
        "providers": [(p, LEGEND[p], SERIES.index(p) + 1) for p in providers],
        "empty": peak <= 0,
    }


def report(period: str) -> dict:
    period = period if period in PERIODS else "day"
    series = buckets(period)
    since = series[0].start
    return {
        "period": period,
        "periods": [(key, value[0], value[1]) for key, value in PERIODS.items()],
        "span": f"last {PERIODS[period][1]} {PERIODS[period][0].lower()}",
        "totals": totals(),
        "billed_chart": chart(series, BILLED),
        "plans_chart": chart(series, PLANS),
        "rows": [
            {
                "label": bucket.label,
                "values": [format_usd(bucket.values[p]) for p in SERIES],
                "plans": format_usd(bucket.plans),
            }
            for bucket in reversed(series)
        ],
        "series_names": [LEGEND[p] for p in SERIES],
        "breakdown": breakdown(since),
        "caps": budgets.overview(),
        "month": budgets.month_start(),
    }
