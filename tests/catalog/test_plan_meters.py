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
    today = datetime.now(UTC).date()
    renews_on = date(today.year + (today.month // 12), (today.month % 12) + 1, 26)
    PlanAccount.objects.create(
        provider="claude-code",
        account=".claude-2",
        email="almonium.app@gmail.com",
        plan_label="max",
        renews_on=renews_on,
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
    assert meter.session_percent == 12 and meter.renews_on == renews_on
    assert meter.workers == ("main",)

    client.force_login(get_user_model().objects.create_user(username="staff", is_staff=True))
    page = client.get(reverse("catalog:dashboard")).content.decode()
    assert "almonium.app@gmail.com" in page and "worker: main" in page
    assert "Week resets" in page and "Session 12%" in page
    assert f">{renews_on.strftime('%a %-d %b')}</span>" in page
    assert "Paid on the 26th of the month" in page

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


def test_elevenlabs_meter_reads_subscription_and_fallback_dotenv(tmp_path, settings):
    import io
    import json

    from almonium_book_processor.ai.elevenlabs_meter import elevenlabs_api_key, elevenlabs_meter

    settings.ELEVENLABS_API_KEY = ""
    settings.LEXICON_BACKEND_DIR = str(tmp_path)
    (tmp_path / ".env").write_text('ELEVENLABS_API_KEY="sk_test_123"\n', encoding="utf-8")
    assert elevenlabs_api_key() == "sk_test_123"

    settings.ELEVENLABS_API_KEY = "sk_direct"
    assert elevenlabs_api_key() == "sk_direct"

    payload = {
        "tier": "starter",
        "character_count": 1200,
        "character_limit": 62056,
        "next_character_count_reset_unix": 1796233495,
        "next_invoice": {"amount_due_cents": 720},
        "currency": "usd",
    }

    class FakeResponse(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    seen = {}

    def fake_open(request, timeout=0):
        seen["url"] = request.full_url
        seen["key"] = request.get_header("Xi-api-key")
        return FakeResponse(json.dumps(payload).encode("utf-8"))

    meter = elevenlabs_meter(opener=fake_open)
    assert seen == {
        "url": "https://api.elevenlabs.io/v1/user/subscription",
        "key": "sk_direct",
    }
    assert meter is not None
    assert meter["used_percent"] == 2
    assert meter["units_used"] == 1200
    assert meter["units_limit"] == 62056
    assert meter["resets_at"] == datetime(2026, 12, 2, 17, 44, 55, tzinfo=UTC)
    assert meter["plan_label"] == "Starter · $7.20/mo"
    assert meter["renews_on"].day == 2

    def broken(request, timeout=0):
        raise OSError("offline")

    assert elevenlabs_meter(opener=broken) is None
    assert elevenlabs_meter(api_key="") is None


def test_elevenlabs_shows_on_dashboard_as_readonly_monthly_meter_and_skips_routing(
    settings, monkeypatch
):
    from datetime import date
    from io import StringIO

    from django.core.management import call_command

    from almonium_book_processor.ai import elevenlabs_meter as elevenlabs_mod
    from almonium_book_processor.catalog.models import PlanAccount, PlanWorker
    from almonium_book_processor.catalog.plan_meters import plan_routing

    settings.AI_PLANS = ""
    settings.CODEX_HOMES = []
    settings.CLAUDE_CONFIG_DIRS = []
    settings.ELEVENLABS_API_KEY = "sk_live_test"
    monkeypatch.setattr(
        "almonium_book_processor.catalog.management.commands.plan_meter.codex_meter",
        lambda **kwargs: None,
    )
    monkeypatch.setattr(
        "almonium_book_processor.catalog.management.commands.plan_meter.claude_meter",
        lambda **kwargs: None,
    )
    monkeypatch.setattr(
        elevenlabs_mod,
        "elevenlabs_meter",
        lambda: {
            "used_percent": 0,
            "units_used": 0,
            "units_limit": 62056,
            "resets_at": datetime(2026, 12, 2, 17, 44, 55, tzinfo=UTC),
            "plan_type": "starter",
            "plan_label": "Starter · $7.20/mo",
            "renews_on": date(2026, 12, 2),
        },
    )

    out = StringIO()
    call_command("plan_meter", "--record", stdout=out)
    assert "elevenlabs (starter): 0% of the month used, 0 of 62,056 chars" in out.getvalue()

    reading("codex", ".codex", 10)
    PlanWorker.objects.create(name="main", nodename="plans-main@yoga", seen_at=datetime.now(UTC))

    meters = plan_meters()
    assert [m.provider for m in meters] == ["codex", "elevenlabs"]
    eleven = meters[1]
    assert eleven.is_monthly and not eleven.is_routable
    assert eleven.units_left == 62056 and eleven.workers == ()
    assert eleven.plan_label == "Starter · $7.20/mo"
    assert PlanAccount.objects.get(provider="elevenlabs").renews_on == date(2026, 12, 2)
    assert [p["provider"] for p in plan_routing(meters)] == ["codex"]

    # An increase in units_used marks ElevenLabs as in use even within the same integer percent.
    earlier = PlanMeterReading.objects.get(provider="elevenlabs")
    PlanMeterReading.objects.filter(pk=earlier.pk).update(
        created_at=datetime.now(UTC) - timedelta(minutes=10)
    )
    reading("elevenlabs", "api", 0, units_used=250, units_limit=62056)
    assert plan_meters()[1].used_by == ("other use",)

    staff = get_user_model().objects.create_user("staff", password="x", is_staff=True)
    client = Client()
    client.force_login(staff)
    page = client.get(reverse("catalog:dashboard")).content.decode()

    assert "<strong>ElevenLabs</strong> <code>api</code>" in page
    assert "Starter · $7.20/mo" in page
    assert "Month 0% used" in page
    assert "61\u202f806 of 62\u202f056 chars left" in page
    assert "Wed 2 Dec" in page
    assert "Read-only meter" in page
    assert 'name="provider" value="elevenlabs"' not in page
