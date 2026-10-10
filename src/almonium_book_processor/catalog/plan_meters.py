"""The plan accounts' meters as the pages show them: the last reading of each account."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from django.utils import timezone

from almonium_book_processor.ai.pricing import PLAN_WEEK_USD
from almonium_book_processor.catalog.models import PlanMeterReading

PROVIDER_LABELS = {"codex": "Codex", "claude-code": "Claude"}


@dataclass(frozen=True)
class PlanMeter:
    provider: str
    account: str
    week_percent: int
    read_at: datetime
    resets_at: datetime | None
    fable_week_percent: int | None

    @property
    def provider_label(self) -> str:
        return self.label(self.provider)

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
    def stale(self) -> bool:
        """A reading older than an hour: the timer or the host is not running."""

        return timezone.now() - self.read_at > timezone.timedelta(hours=1)


def plan_meters() -> list[PlanMeter]:
    """The last reading of every account, Codex first, then by account name."""

    latest: dict[tuple[str, str], PlanMeterReading] = {}
    for reading in PlanMeterReading.objects.order_by("-created_at")[:200]:
        latest.setdefault((reading.provider, reading.account), reading)
    meters = [
        PlanMeter(
            provider=reading.provider,
            account=reading.account,
            week_percent=reading.week_percent,
            read_at=reading.created_at,
            resets_at=reading.resets_at,
            fable_week_percent=reading.fable_week_percent,
        )
        for reading in latest.values()
    ]
    return sorted(meters, key=lambda meter: (meter.provider != "codex", meter.account))
