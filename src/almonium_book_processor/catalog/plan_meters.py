"""The plan accounts' meters as the pages show them: the last reading of each account."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal

from django.utils import timezone

from almonium_book_processor.ai.pricing import PLAN_WEEK_USD
from almonium_book_processor.catalog.models import (
    AIRun,
    LexiconWriter,
    PlanAccount,
    PlanAccountPause,
    PlanMeterReading,
    PlanWorker,
)

PROVIDER_LABELS = {"codex": "Codex", "claude-code": "Claude", "antigravity": "Gemini"}
# A call recorded on an account this recently counts as the books using it now: a chapter's
# call takes minutes, and a step between two calls is still the same work.
IN_USE_WITHIN = timedelta(minutes=15)


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
    pause_note: str = ""
    # The week's share at which the account pauses itself; None is no limit.
    pause_at_percent: int | None = None
    session_percent: int | None = None
    session_resets_at: datetime | None = None
    # Whose account, what plan and when it renews (PlanAccount; the renewal date is the owner's).
    email: str = ""
    plan_label: str = ""
    renews_on: date | None = None
    # The plan workers that may call this account: all of them, since the accounts are pooled.
    workers: tuple[str, ...] = ()
    # Where the account stands among its plan's when calls go in order; 1 is spent first.
    priority: int | None = None
    # What is using the account now: "books" (a model call recorded on it in the last quarter
    # of an hour, or its meter rising while a call on its plan is under way), "entries" (a
    # dictionary writer running on it), or, with neither, "other use" when its meter rose
    # between the last two readings (a chat session, a run started by hand).
    used_by: tuple[str, ...] = ()

    @property
    def in_use(self) -> bool:
        return bool(self.used_by)

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
    def paused_at_limit(self) -> bool:
        from almonium_book_processor.catalog.plan_pause import limit_note

        return (
            self.paused
            and self.pause_at_percent is not None
            and self.pause_note == limit_note(self.pause_at_percent)
        )

    @property
    def stale(self) -> bool:
        """A reading older than an hour: the timer or the host is not running."""

        return timezone.now() - self.read_at > timezone.timedelta(hours=1)


def plan_meters() -> list[PlanMeter]:
    """The last reading of every account, Codex first, then by account name."""

    paused = {
        (provider, account): note
        for provider, account, note in PlanAccountPause.objects.values_list(
            "provider", "account", "note"
        )
    }
    details = {(a.provider, a.account): a for a in PlanAccount.objects.all()}
    # every worker calls whichever account of a plan is open, so each serves all of them
    every_worker = tuple(PlanWorker.objects.order_by("name").values_list("name", flat=True))
    # Each account's own last reading, however old: an account whose meter cannot be read
    # (a lapsed login) stays on the page as stale instead of dropping out of it.
    latest: dict[tuple[str, str], PlanMeterReading] = {}
    for pair in PlanMeterReading.objects.order_by().values_list("provider", "account").distinct():
        reading = (
            PlanMeterReading.objects.filter(provider=pair[0], account=pair[1])
            .order_by("-created_at")
            .first()
        )
        if reading is not None:
            latest[pair] = reading
    since = timezone.now() - IN_USE_WITHIN
    on_books = set(
        AIRun.objects.filter(updated_at__gte=since)
        .exclude(plan_account="")
        .values_list("model_configuration__provider", "plan_account")
        .distinct()
    )
    calling = set(
        AIRun.objects.filter(status=AIRun.Status.SUBMITTED, updated_at__gte=since)
        .values_list("model_configuration__provider", flat=True)
        .distinct()
    )
    on_entries = {
        ("claude-code", account)
        for account in LexiconWriter.objects.filter(running=True, state="active").values_list(
            "account", flat=True
        )
    }
    meters = []
    for key, reading in latest.items():
        about = details.get(key)
        used_by = tuple(
            name for name, users in (("books", on_books), ("entries", on_entries)) if key in users
        )
        if not used_by and _rising(reading):
            # a call still under way has no account yet: a rising meter on a plan the books
            # are calling now is theirs
            used_by = ("books",) if reading.provider in calling else ("other use",)
        meters.append(
            PlanMeter(
                provider=reading.provider,
                account=reading.account,
                week_percent=reading.week_percent,
                read_at=reading.created_at,
                resets_at=reading.resets_at,
                fable_week_percent=reading.fable_week_percent,
                paused=key in paused,
                pause_note=paused.get(key, ""),
                pause_at_percent=about.pause_at_percent if about else None,
                session_percent=reading.session_percent,
                session_resets_at=reading.session_resets_at,
                email=about.email if about else "",
                plan_label=(about.plan_label if about else "") or reading.plan_type or "",
                renews_on=about.renews_on if about else None,
                workers=every_worker,
                priority=about.priority if about else None,
                used_by=used_by,
            )
        )
    return sorted(meters, key=lambda meter: (meter.provider != "codex", meter.account))


def _rising(reading: PlanMeterReading) -> bool:
    """Whether a fresh reading stands above the one before it, in the week or in the session."""

    if timezone.now() - reading.created_at > timedelta(hours=1):
        return False
    before = (
        PlanMeterReading.objects.filter(
            provider=reading.provider,
            account=reading.account,
            created_at__lt=reading.created_at,
            created_at__gte=reading.created_at - timedelta(hours=1),
        )
        .order_by("-created_at")
        .first()
    )
    if before is None:
        return False
    return reading.week_percent > before.week_percent or (
        reading.session_percent is not None
        and before.session_percent is not None
        and reading.session_percent > before.session_percent
    )


def plan_routing(meters: list[PlanMeter]) -> list[dict]:
    """Each plan's way of choosing among its accounts, with the accounts in the order calls
    try them when they go in order (an account without a priority last, by name)."""

    from almonium_book_processor.catalog.models import PlanRouting

    modes = dict(PlanRouting.objects.values_list("provider", "mode"))
    plans = []
    for provider in PROVIDER_LABELS:
        own = sorted(
            (meter for meter in meters if meter.provider == provider),
            key=lambda meter: (meter.priority is None, meter.priority or 0, meter.account),
        )
        if not own:
            continue
        mode = modes.get(provider, PlanRouting.Mode.ORDER)
        plans.append(
            {
                "provider": provider,
                "label": PlanMeter.label(provider),
                "mode": mode,
                "balanced": mode == PlanRouting.Mode.BALANCED,
                "accounts": own,
            }
        )
    return plans
