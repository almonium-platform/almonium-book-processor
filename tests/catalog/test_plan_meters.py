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


def test_an_account_whose_meter_stopped_answering_stays_on_the_page_as_stale():
    """A lapsed login leaves its last reading days behind the others; it must not drop out."""

    lapsed = reading("claude-code", ".claude-2", 7)
    PlanMeterReading.objects.filter(pk=lapsed.pk).update(
        created_at=datetime.now(UTC) - timedelta(days=4)
    )
    for _ in range(250):
        reading("codex", ".codex", 10)

    meters = {meter.account: meter for meter in plan_meters()}
    assert set(meters) == {".codex", ".claude-2"}
    assert meters[".claude-2"].stale and meters[".claude-2"].week_percent == 7


def test_the_catalogue_page_shows_the_plans_this_week():
    user = get_user_model().objects.create_user("staff", password="x", is_staff=True)
    client = Client()
    client.force_login(user)
    reading("codex", ".codex-2", 12, plan_type="prolite")

    page = client.get(reverse("catalog:dashboard")).content.decode()

    assert "Plans this week" in page
    assert "<strong>Codex</strong> <code>.codex-2</code>" in page
    # The header carries the short form inline; the popover keeps the account.
    assert 'class="plan-meter-inline">Codex-2 <span class="run-bar">' in page
    assert "12% used" in page


def test_each_account_shows_who_it_is_when_it_resets_and_when_it_renews(client):
    from datetime import date

    from almonium_book_processor.catalog.models import PlanAccount, PlanWorker

    reading(
        "claude-code",
        ".claude-2",
        3,
        session_percent=12,
        resets_at=datetime(2026, 10, 26, 20, 0, tzinfo=UTC),
        session_resets_at=datetime(2026, 10, 26, 4, 0, tzinfo=UTC),
    )
    PlanAccount.objects.create(
        provider="claude-code",
        account=".claude-2",
        email="almonium.app@gmail.com",
        plan_label="max",
        renews_on=date(2026, 11, 26),
    )
    PlanWorker.objects.create(
        name="main",
        nodename="plans-main@yoga",
        codex_account=".codex",
        claude_account=".claude-2",
        seen_at=datetime.now(UTC),
    )

    (meter,) = plan_meters()
    assert meter.email == "almonium.app@gmail.com" and meter.plan_label == "max"
    assert meter.session_percent == 12 and meter.renews_on == date(2026, 11, 26)
    assert meter.workers == ("main",)

    client.force_login(get_user_model().objects.create_user(username="staff", is_staff=True))
    page = client.get(reverse("catalog:dashboard")).content.decode()
    assert "almonium.app@gmail.com" in page and "worker: main" in page
    assert "Week resets" in page and "Session 12%" in page
    assert ">Thu 26 Nov</span>" in page and "Paid on the 26th of the month" in page

    response = client.post(
        reverse("catalog:plan-account-details"),
        {"provider": "claude-code", "account": ".claude-2", "renews_on": "2026-12-26"},
    )
    assert response.status_code == 302
    assert PlanAccount.objects.get(account=".claude-2").renews_on == date(2026, 12, 26)


def test_the_renewal_date_rolls_forward_a_month_at_a_time():
    from datetime import date

    from almonium_book_processor.catalog.plan_meters import PlanMeter

    bought = PlanMeter("claude-code", ".claude-2", 0, datetime.now(UTC), None, None)
    assert bought.renews_next is None
    old = PlanMeter(
        "codex", ".codex-2", 0, datetime.now(UTC), None, None, renews_on=date(2026, 1, 31)
    )
    nxt = old.renews_next
    assert nxt >= datetime.now(UTC).date() and nxt.day in (28, 29, 30, 31)


def test_an_account_says_what_is_using_it_now():
    from almonium_book_processor.catalog.models import (
        AIRun,
        LexiconWriter,
        ModelConfiguration,
        PromptTemplate,
    )

    for account in (".codex", ".codex-2"):
        reading("codex", account, 10)
    for account in (".claude", ".claude-2"):
        reading("claude-code", account, 10, session_percent=20)
    # a chat session moved this one's meter since the reading before
    earlier = reading("antigravity", "antigravity-cli", 3, session_percent=5)
    PlanMeterReading.objects.filter(pk=earlier.pk).update(
        created_at=datetime.now(UTC) - timedelta(minutes=15)
    )
    reading("antigravity", "antigravity-cli", 3, session_percent=9)

    configuration = ModelConfiguration.objects.create(
        name="codex-translation-v1", provider="codex", model="gpt-6.1-sol", purpose="p"
    )
    prompt = PromptTemplate.objects.create(
        name="p", version=1, purpose="p", system_prompt="s", user_template="u"
    )
    for account, minutes_ago in ((".codex", 2), (".codex-2", 40)):
        run = AIRun.objects.create(
            model_configuration=configuration,
            prompt_template=prompt,
            idempotency_key=account,
            status=AIRun.Status.SUCCEEDED,
            plan_account=account,
        )
        AIRun.objects.filter(pk=run.pk).update(
            updated_at=datetime.now(UTC) - timedelta(minutes=minutes_ago)
        )
    LexiconWriter.objects.create(
        account=".claude-2", language="en", word_list="healthy", running=True, state="active"
    )
    LexiconWriter.objects.create(
        account=".claude", language="de", word_list="healthy", running=False, state="inactive"
    )

    using = {meter.account: meter.used_by for meter in plan_meters()}

    assert using == {
        ".codex": ("books",),
        ".codex-2": (),  # its last call was forty minutes ago
        ".claude": (),  # its writer is off
        ".claude-2": ("entries",),
        "antigravity-cli": ("other use",),
    }

    # a call under way has no account yet: the plan's rising meter is the books'
    gemini = ModelConfiguration.objects.create(
        name="antigravity-translation", provider="antigravity", model="gemini-4-neon", purpose="p"
    )
    AIRun.objects.create(
        model_configuration=gemini,
        prompt_template=prompt,
        idempotency_key="under-way",
        status=AIRun.Status.SUBMITTED,
    )
    assert {m.account: m.used_by for m in plan_meters()}["antigravity-cli"] == ("books",)


def test_the_dashboard_marks_the_accounts_in_use():
    reading("codex", ".codex", 10)
    earlier = reading("codex", ".codex-2", 3)
    PlanMeterReading.objects.filter(pk=earlier.pk).update(
        created_at=datetime.now(UTC) - timedelta(minutes=15)
    )
    reading("codex", ".codex-2", 5)
    staff = get_user_model().objects.create_user("staff", password="x", is_staff=True)
    client = Client()
    client.force_login(staff)

    page = client.get(reverse("catalog:dashboard")).content.decode()

    assert page.count("plan-meter-inline plan-meter-in-use") == 1
    assert "In use now: other use" in page
