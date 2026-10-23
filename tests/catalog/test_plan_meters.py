from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse

from almonium_book_processor.catalog.models import PlanMeterReading
from almonium_book_processor.catalog.plan_meters import plan_meters

pytestmark = pytest.mark.django_db


def reading(provider, account, week, **fields):
    return PlanMeterReading.objects.create(
        provider=provider, account=account, week_percent=week, **fields
    )


def test_the_last_reading_of_each_account_is_shown_codex_first():
    reading("claude-code", ".claude", 45, fable_week_percent=29)
    reading("codex", ".codex-2", 0)
    old = reading("codex", ".codex", 30)
    PlanMeterReading.objects.filter(pk=old.pk).update(
        created_at=datetime.now(UTC) - timedelta(hours=3)
    )
    reading("codex", ".codex", 35, resets_at=datetime(2026, 10, 14, 20, 26, tzinfo=UTC))

    meters = plan_meters()

    assert [(m.provider, m.account, m.week_percent) for m in meters] == [
        ("codex", ".codex", 35),
        ("codex", ".codex-2", 0),
        ("claude-code", ".claude", 45),
    ]
    codex = meters[0]
    # a point of the week is a share of the plan's price: $100 a month, 12 months, 52 weeks
    assert codex.week_usd == Decimal(100) * 12 / 52
    assert codex.spent_usd == codex.week_usd * 35 / 100
    assert not codex.stale
    assert meters[2].fable_week_percent == 29


def test_a_reading_older_than_an_hour_is_marked_stale():
    old = reading("codex", ".codex", 10)
    PlanMeterReading.objects.filter(pk=old.pk).update(
        created_at=datetime.now(UTC) - timedelta(hours=2)
    )

    assert plan_meters()[0].stale


def test_the_catalogue_page_shows_the_plans_this_week():
    user = get_user_model().objects.create_user("staff", password="x", is_staff=True)
    client = Client()
    client.force_login(user)
    reading("codex", ".codex-2", 12, plan_type="prolite")

    page = client.get(reverse("catalog:dashboard")).content.decode()

    assert "Plans this week" in page
    assert "Codex <small>.codex-2</small>" in page
    # The header carries the short form inline; the popover keeps the account.
    assert 'class="plan-meter-inline">Codex-2 <span class="run-bar">' in page
    assert "12% used" in page
