"""Modal is used only inside its free monthly credits; past the budget a run embeds locally.

The owner pays nothing for Modal: the Starter plan's monthly credits are the whole budget.
Before an offline alignment starts on Modal, this month's recorded GPU spend and the run's
own estimate are compared with MODAL_MONTHLY_BUDGET_USD, set under the credits because what
a run records is an estimate. A run that would pass it embeds on the worker's CPU instead:
slower, free, and never held. The workspace budget on Modal's Usage & Billing page is the
hard cap behind this one.
"""

from __future__ import annotations

from decimal import Decimal

from django.conf import settings
from django.utils import timezone

from almonium_book_processor.catalog.models import PipelineRun


def month_start():
    now = timezone.now()
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def spent_this_month() -> Decimal:
    """What offline alignment runs recorded on Modal since the first of the month (UTC)."""

    return sum(
        (
            Decimal(str(usd or "0"))
            for usd in PipelineRun.objects.filter(
                stage=PipelineRun.Stage.ALIGN,
                updated_at__gte=month_start(),
                summary__embedding__modal_calls__gt=0,
            ).values_list("summary__embedding__usd", flat=True)
        ),
        Decimal("0"),
    )


def allows(estimate_usd: Decimal | None) -> bool:
    """Whether a run that expects to cost this still fits in this month's budget."""

    budget = Decimal(str(settings.MODAL_MONTHLY_BUDGET_USD))
    return spent_this_month() + (estimate_usd or Decimal("0")) <= budget
