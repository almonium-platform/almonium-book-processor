from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from almonium_book_processor.catalog.models import AIRun, Edition, EditionTombstone
from almonium_book_processor.catalog.spend import (
    edition_spend,
    format_usd,
    spend_by_work,
    work_spend,
)
from tests.catalog.test_ai_spend import edition, run

pytestmark = pytest.mark.django_db


def sibling(original: Edition, slug: str, language: str, level: str = "") -> Edition:
    return Edition.objects.create(
        slug=slug,
        work=original.work,
        source_edition=original,
        title=original.title,
        author=original.author,
        language=language,
        cefr_level=level or None,
        edition_type="adaptation" if level else "machine_translation",
        parallel_role="parallel",
        source_sha256="d" * 64,
    )


def test_format_usd_keeps_fractions_of_a_cent_visible() -> None:
    assert format_usd(None) == "$0"
    assert format_usd(Decimal("4.375829")) == "$4.38"
    assert format_usd(Decimal("0.000609")) == "$0.0006"


def test_edition_and_work_spend_sum_the_ledger_including_removed_editions() -> None:
    original = edition()
    adapted = sibling(original, "spend-work-en-b2", "en", "B2")
    run(
        original,
        purpose="chapter-analysis",
        model="luna",
        input_tokens=10,
        output_tokens=5,
        cost="0.5",
    )
    run(
        original,
        purpose="chapter-analysis",
        model="luna",
        input_tokens=10,
        output_tokens=5,
        cost="0.25",
    )
    run(
        adapted,
        purpose="level_adaptation",
        model="terra",
        input_tokens=100,
        output_tokens=50,
        cost="3",
    )
    run(
        adapted,
        purpose="adaptation_fidelity",
        model="terra",
        input_tokens=1,
        output_tokens=1,
        cost=None,
        status=AIRun.Status.FAILED,
    )
    tombstone = EditionTombstone.objects.create(
        edition_id="00000000-0000-0000-0000-000000000001",
        edition_slug="spend-work-uk",
        work_slug=original.work.slug,
        title=original.title,
        author=original.author,
        language="uk",
        edition_type="machine_translation",
        reason="quality",
    )
    AIRun.objects.create(
        tombstone=tombstone,
        model_configuration=AIRun.objects.first().model_configuration,
        prompt_template=AIRun.objects.first().prompt_template,
        status=AIRun.Status.SUCCEEDED,
        estimated_cost_usd=Decimal("2"),
    )

    mine = edition_spend(adapted)
    assert (mine["calls"], mine["usd"], mine["usd_label"]) == (2, Decimal("3"), "$3.00")
    assert [(line["purpose"], line["calls"], line["usd_label"]) for line in mine["lines"]] == [
        ("Level adaptation", 1, "$3.00"),
        ("Fidelity audit", 1, "$0"),
    ]

    whole = work_spend(original.work)
    assert (whole["calls"], whole["usd_label"]) == (5, "$5.75")
    assert [(row["slug"], row["removed"], row["usd_label"]) for row in whole["editions"]] == [
        ("spend-work-en-b2", False, "$3.00"),
        ("spend-work-uk", True, "$2.00"),
        ("spend-work-en", False, "$0.75"),
    ]
    assert spend_by_work([original.work]) == {original.work.id: "$5.75"}


def test_edition_page_and_dashboard_show_the_spend(client) -> None:
    original = edition()
    adapted = sibling(original, "spend-work-en-b2", "en", "B2")
    run(
        original,
        purpose="chapter-analysis",
        model="luna",
        input_tokens=10,
        output_tokens=5,
        cost="0.5",
    )
    run(
        adapted,
        purpose="level_adaptation",
        model="terra",
        input_tokens=100,
        output_tokens=50,
        cost="3",
    )
    client.force_login(get_user_model().objects.create_user(username="staff", is_staff=True))

    page = client.get(reverse("catalog:edition-detail", args=[adapted.id]))
    assert page.status_code == 200
    assert page.context["spend"]["edition"]["usd_label"] == "$3.00"
    assert page.context["spend"]["work"]["usd_label"] == "$3.50"
    html = page.content.decode()
    assert 'href="#ai-spend"' in html
    assert "Level adaptation" in html
    assert "Whole work · $3.50" in html

    dashboard = client.get(reverse("catalog:dashboard"))
    assert "$3.50 AI" in dashboard.content.decode()
    group = next(g for g in dashboard.context["groups"] if g.work == original.work)
    assert group.spend_label == "$3.50"
