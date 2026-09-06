from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from django.db.models import Count, Sum

from almonium_book_processor.catalog.models import AIRun

# The column's own scale, so the sum reads the same whichever database summed it.
CENTS_OF_A_CENT = Decimal("0.000001")


def ai_spend(since: datetime, until: datetime) -> dict[str, Any]:
    """What the model calls in the window cost, one line per purpose and model.

    Every run counts, whatever its status: a batch that failed after the provider
    metered it still cost what the row says. The dollars are the estimates each
    pipeline stored at the time, priced with the table it had then.
    """

    rows = (
        AIRun.objects.filter(created_at__gte=since, created_at__lt=until)
        .values("model_configuration__purpose", "model_configuration__model")
        .annotate(
            runs=Count("id"),
            input_tokens=Sum("input_tokens"),
            cached_input_tokens=Sum("cached_input_tokens"),
            output_tokens=Sum("output_tokens"),
            reasoning_tokens=Sum("reasoning_tokens"),
            estimated_cost_usd=Sum("estimated_cost_usd"),
        )
        .order_by("model_configuration__purpose", "model_configuration__model")
    )
    return {
        "since": since.isoformat(),
        "until": until.isoformat(),
        "lines": [
            {
                "purpose": row["model_configuration__purpose"],
                "model": row["model_configuration__model"],
                "runs": row["runs"],
                "input_tokens": row["input_tokens"] or 0,
                "cached_input_tokens": row["cached_input_tokens"] or 0,
                "output_tokens": row["output_tokens"] or 0,
                "reasoning_tokens": row["reasoning_tokens"] or 0,
                "estimated_cost_usd": str(
                    (row["estimated_cost_usd"] or Decimal("0")).quantize(CENTS_OF_A_CENT)
                ),
            }
            for row in rows
        ],
    }
