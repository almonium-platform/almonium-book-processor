from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from django.db.models import Count, Q, Sum

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


PURPOSE_LABELS = {
    "level_adaptation": "Level adaptation",
    "adaptation_fidelity": "Fidelity audit",
    "adaptation_difficulty": "Difficulty judge",
    "literary_translation": "Translation",
    "metadata_translation": "Title page translation",
    "alignment_adjudication": "Alignment adjudication",
    "chapter-analysis": "Chapter analysis",
    "sentence_alignment": "Sentence alignment preview",
    "import_metadata": "Metadata detection",
    "description": "Description",
}


def purpose_label(purpose: str) -> str:
    return PURPOSE_LABELS.get(purpose, purpose.replace("_", " ").replace("-", " ").capitalize())


def format_usd(value) -> str:
    """Dollars as an operator reads them: cents, or the fraction when there are none."""

    amount = Decimal(value or 0)
    if amount == 0:
        return "$0"
    if amount < Decimal("0.01"):
        return f"${amount.quantize(Decimal('0.0001'))}"
    return f"${amount.quantize(Decimal('0.01'))}"


def _lines(runs) -> list[dict[str, Any]]:
    rows = (
        runs.values("model_configuration__purpose", "model_configuration__model")
        .annotate(
            calls=Count("id"),
            input_tokens=Sum("input_tokens"),
            output_tokens=Sum("output_tokens"),
            usd=Sum("estimated_cost_usd"),
        )
        .order_by("-usd", "model_configuration__purpose")
    )
    return [
        {
            "purpose": purpose_label(row["model_configuration__purpose"]),
            "model": row["model_configuration__model"],
            "calls": row["calls"],
            "input_tokens": row["input_tokens"] or 0,
            "output_tokens": row["output_tokens"] or 0,
            "usd": row["usd"] or Decimal("0"),
            "usd_label": format_usd(row["usd"]),
        }
        for row in rows
    ]


def _totals(runs) -> dict[str, Any]:
    totals = runs.aggregate(calls=Count("id"), usd=Sum("estimated_cost_usd"))
    return {
        "calls": totals["calls"],
        "usd": totals["usd"] or Decimal("0"),
        "usd_label": format_usd(totals["usd"]),
    }


def edition_spend(edition) -> dict[str, Any]:
    """Every model call billed to this edition, in this environment's ledger.

    An edition promoted from another environment was processed there; its
    calls sit in that ledger, so the figure here is what this stack paid.
    """

    runs = AIRun.objects.filter(edition=edition)
    return {**_totals(runs), "lines": _lines(runs)}


def work_spend(work) -> dict[str, Any]:
    """The work's calls across its editions, purged ones included.

    A purge keeps the ledger rows and points them at a tombstone that
    remembers the work's slug, so the money spent on a removed edition still
    counts toward the book it belonged to.
    """

    runs = AIRun.objects.filter(Q(edition__work=work) | Q(tombstone__work_slug=work.slug))
    by_edition = (
        runs.values(
            "edition_id",
            "edition__slug",
            "edition__language",
            "edition__cefr_level",
            "edition__edition_type",
            "tombstone__edition_slug",
            "tombstone__language",
        )
        .annotate(calls=Count("id"), usd=Sum("estimated_cost_usd"))
        .order_by("-usd")
    )
    return {
        **_totals(runs),
        "lines": _lines(runs),
        "editions": [
            {
                "edition_id": row["edition_id"],
                "slug": row["edition__slug"] or row["tombstone__edition_slug"],
                "language": row["edition__language"] or row["tombstone__language"],
                "cefr_level": row["edition__cefr_level"],
                "edition_type": row["edition__edition_type"],
                "removed": row["edition_id"] is None,
                "calls": row["calls"],
                "usd": row["usd"] or Decimal("0"),
                "usd_label": format_usd(row["usd"]),
            }
            for row in by_edition
        ],
    }


def spend_by_work(works) -> dict[Any, str]:
    """One label per work id for a listing, from two grouped queries."""

    slugs = {work.slug: work.id for work in works}
    totals: dict[Any, Decimal] = {}
    for row in (
        AIRun.objects.filter(edition__work__in=works)
        .values("edition__work_id")
        .annotate(usd=Sum("estimated_cost_usd"))
    ):
        totals[row["edition__work_id"]] = row["usd"] or Decimal("0")
    for row in (
        AIRun.objects.filter(tombstone__work_slug__in=slugs)
        .values("tombstone__work_slug")
        .annotate(usd=Sum("estimated_cost_usd"))
    ):
        work_id = slugs[row["tombstone__work_slug"]]
        totals[work_id] = totals.get(work_id, Decimal("0")) + (row["usd"] or Decimal("0"))
    return {work_id: format_usd(usd) for work_id, usd in totals.items()}
