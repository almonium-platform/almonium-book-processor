"""The plan accounts' meters as the pages show them: the last reading of each account."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal

from django.utils import timezone

from almonium_book_processor.ai.pricing import PLAN_WEEK_USD
from almonium_book_processor.catalog.models import PlanAccount, PlanMeterReading, PlanWorker

PROVIDER_LABELS = {"codex": "Codex", "claude-code": "Claude"}


@dataclass(frozen=True)
class PlanMeter:
    provider: str
    account: str
    week_percent: int
    read_at: datetime
    resets_at: datetime | None
    fable_week_percent: int | None
    # Whether the owner has taken this account out of the pipeline (catalog/plan_pause.py).
    paused: bool = False
    session_percent: int | None = None
    session_resets_at: datetime | None = None
    # Whose account, what plan and when it renews (PlanAccount; the renewal date is the owner's).
    email: str = ""
    plan_label: str = ""
    renews_on: date | None = None
    # The plan workers that work on this account.
    workers: tuple[str, ...] = ()

    @property
    def provider_label(self) -> str:
        return self.label(self.provider)

    @property
    def short_label(self) -> str:
        """The provider, numbered when it is a second seat: Codex, Codex-2, Claude."""

        seat = re.search(r"-(\d+)$", self.account)
        return f"{self.provider_label}-{seat.group(1)}" if seat else self.provider_label

    @staticmethod
    def label(provider: str) -> str:
        return PROVIDER_LABELS.get(provider, provider)

    @property
    def week_usd(self) -> Decimal:
        return PLAN_WEEK_USD.get(self.provider, Decimal(0))

    @property
    def spent_usd(self) -> Decimal:
        return self.week_usd * self.week_percent / 100

    @property
    def left_usd(self) -> Decimal:
        return self.week_usd - self.spent_usd

    @property
    def renews_next(self) -> date | None:
        """The next renewal: the saved date rolled forward a month at a time until it is ahead."""

        if self.renews_on is None:
            return None
        today = timezone.localdate()
        year, month, day = self.renews_on.year, self.renews_on.month, self.renews_on.day
        when = self.renews_on
        while when < today:
            month += 1
            if month > 12:
                month, year = 1, year + 1
            last = (date(year + (month == 12), month % 12 + 1, 1) - timedelta(days=1)).day
            when = date(year, month, min(day, last))
        return when

    @property
    def stale(self) -> bool:
        """A reading older than an hour: the timer or the host is not running."""

        return timezone.now() - self.read_at > timezone.timedelta(hours=1)


def plan_meters() -> list[PlanMeter]:
    """The last reading of every account, Codex first, then by account name."""

    from almonium_book_processor.catalog.plan_pause import paused_accounts

    paused = paused_accounts()
    details = {(a.provider, a.account): a for a in PlanAccount.objects.all()}
    workers: dict[tuple[str, str], list[str]] = {}
    for worker in PlanWorker.objects.order_by("name"):
        workers.setdefault(("codex", worker.codex_account), []).append(worker.name)
        workers.setdefault(("claude-code", worker.claude_account), []).append(worker.name)
    latest: dict[tuple[str, str], PlanMeterReading] = {}
    for reading in PlanMeterReading.objects.order_by("-created_at")[:200]:
        latest.setdefault((reading.provider, reading.account), reading)
    meters = []
    for key, reading in latest.items():
        about = details.get(key)
        meters.append(
            PlanMeter(
                provider=reading.provider,
                account=reading.account,
                week_percent=reading.week_percent,
                read_at=reading.created_at,
                resets_at=reading.resets_at,
                fable_week_percent=reading.fable_week_percent,
                paused=key in paused,
                session_percent=reading.session_percent,
                session_resets_at=reading.session_resets_at,
                email=about.email if about else "",
                plan_label=(about.plan_label if about else "") or reading.plan_type or "",
                renews_on=about.renews_on if about else None,
                workers=tuple(workers.get(key, ())),
            )
        )
    return sorted(meters, key=lambda meter: (meter.provider != "codex", meter.account))
