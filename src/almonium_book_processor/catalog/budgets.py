"""What each provider has cost this month, and the cap past which it is not asked again.

One place answers both for every provider the pipeline pays: the metered OpenAI API and
Modal's GPUs (money), and the Claude and Codex plans (their calls valued at what the API
would have charged; the plans' own weekly meters still decide when they are full). The
owner sets a monthly cap per provider on the dashboard; no cap means none.

A cap is a hold, never a failure of the book. Before a paid call ``check`` raises
``BudgetReached``, which is an ``AllowanceUsedUp``: every job already records that refusal
in full and every production already waits on it uncounted and tries again, the way it
waits on a plan's wall. Raising the cap, or the first of the next month, lets the next try
through. Modal alone is never held: past its cap an alignment embeds on the worker's CPU
(``allows``).

Months are calendar months in UTC, as the providers bill them.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

from django.conf import settings
from django.db.models import Sum
from django.utils import timezone

from almonium_book_processor.ai.cli_calls import BudgetReached
from almonium_book_processor.catalog.models import AIRun, PipelineRun, ProviderBudget

# provider -> (name on the dashboard, whether it is metered rather than a plan)
PROVIDERS = {
    "openai": ("OpenAI API", True),
    "modal": ("Modal GPU", True),
    "claude-code": ("Claude plan", False),
    "codex": ("Codex plan", False),
    "antigravity": ("Gemini plan", False),
}
# What a provider's dollars are: only the OpenAI API's leave the owner's pocket. Modal runs on
# the workspace's free monthly credits behind a $0 spend limit, so its dollars are credits
# used; the plans are a fixed subscription, their calls valued at API prices.
NOTES = {
    "openai": "paid in dollars",
    "modal": "free credits, not charged",
    "claude-code": "plan, valued at API prices",
    "codex": "plan, valued at API prices",
    "antigravity": "plan, valued at API prices",
}


def month_start(now: datetime | None = None) -> datetime:
    now = now or timezone.now()
    return now.astimezone(UTC).replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def next_month(start: datetime) -> datetime:
    return (
        start.replace(year=start.year + 1, month=1)
        if start.month == 12
        else start.replace(month=start.month + 1)
    )


def spent(provider: str, since: datetime | None = None) -> Decimal:
    """What the provider's calls cost since ``since`` (this month's start by default).

    Modal's is what Modal billed the workspace, every environment together, when its report
    can be read; otherwise what this environment's runs recorded.
    """

    since = since or month_start()
    if provider == "modal":
        from almonium_book_processor.processing import remote_embeddings

        billed = remote_embeddings.billed_by_day(since)
        if billed is not None:
            return sum(billed.values(), Decimal("0"))
        return sum(
            (
                Decimal(str(usd or "0"))
                for usd in PipelineRun.objects.filter(
                    stage=PipelineRun.Stage.ALIGN,
                    updated_at__gte=since,
                    summary__embedding__modal_calls__gt=0,
                ).values_list("summary__embedding__usd", flat=True)
            ),
            Decimal("0"),
        )
    total = AIRun.objects.filter(
        created_at__gte=since, model_configuration__provider=provider
    ).aggregate(usd=Sum("estimated_cost_usd"))["usd"]
    return total or Decimal("0")


def cap(provider: str) -> Decimal | None:
    """The monthly cap the owner set, or for Modal the free credits' default."""

    row = ProviderBudget.objects.filter(provider=provider).first()
    if row is not None:
        return row.monthly_usd
    if provider == "modal":
        return Decimal(str(settings.MODAL_MONTHLY_BUDGET_USD)).quantize(Decimal("0.01"))
    return None


def allows(provider: str, estimate_usd: Decimal | None = None) -> bool:
    """Whether work expected to cost this still fits under the provider's cap."""

    limit = cap(provider)
    if limit is None:
        return True
    used = spent(provider)
    if estimate_usd:
        return used + estimate_usd <= limit
    return used < limit


def check(provider: str, estimate_usd: Decimal | None = None) -> None:
    """Raise ``BudgetReached`` before a call that the provider's cap no longer allows."""

    if allows(provider, estimate_usd):
        return
    start = month_start()
    name = PROVIDERS.get(provider, (provider, True))[0]
    raise BudgetReached(
        f"{name} has cost ${spent(provider):.2f} of its ${cap(provider):.2f} cap for "
        f"{start:%B %Y}. Raise the cap on the dashboard, or it opens again on "
        f"{next_month(start):%-d %B}."
    )


@dataclass(frozen=True)
class Line:
    provider: str
    name: str
    metered: bool
    spent: Decimal
    cap: Decimal | None

    @property
    def share(self) -> int | None:
        if not self.cap:
            return None
        return min(100, int(self.spent * 100 / self.cap))

    @property
    def note(self) -> str:
        return NOTES.get(self.provider, "paid in dollars" if self.metered else "")

    @property
    def reached(self) -> bool:
        return self.cap is not None and self.spent >= self.cap


def overview() -> list[Line]:
    """Every provider's month: what it cost and its cap, money first."""

    since = month_start()
    known = set(PROVIDERS) | set(
        AIRun.objects.filter(created_at__gte=since)
        .exclude(estimated_cost_usd=0)
        .values_list("model_configuration__provider", flat=True)
        .distinct()
    )
    lines = []
    for provider in known:
        name, metered = PROVIDERS.get(provider, (provider, True))
        lines.append(Line(provider, name, metered, spent(provider, since), cap(provider)))
    return sorted(lines, key=lambda line: (not line.metered, line.name))


def set_caps(caps: dict[str, Decimal | None]) -> None:
    for provider, monthly_usd in caps.items():
        ProviderBudget.objects.update_or_create(
            provider=provider, defaults={"monthly_usd": monthly_usd}
        )
