"""A plan account can be paused from the dashboard, and the pause outlives worker restarts."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from almonium_book_processor.catalog import plan_pause
from almonium_book_processor.catalog.models import PlanAccountPause, PlanMeterReading, PlanWorker
from almonium_book_processor.catalog.plan_meters import plan_meters

pytestmark = pytest.mark.django_db


@pytest.fixture
def control(monkeypatch):
    """What the pause tells the workers, instead of the broker."""

    told = []

    class Control:
        def cancel_consumer(self, queue, destination):
            told.append(("stop", tuple(destination)))

        def add_consumer(self, queue, destination):
            told.append(("go", tuple(destination)))

    monkeypatch.setattr("almonium_book_processor.config.celery.app.control", Control())
    return told


@pytest.fixture
def workers(monkeypatch):
    monkeypatch.setenv("PLAN_WORKER_NAME", "main")
    monkeypatch.setenv("CODEX_HOME", "/home/ok/.codex")
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", "/home/ok/.claude-2")
    main = plan_pause.register_worker("plans-main@yoga")
    monkeypatch.setenv("PLAN_WORKER_NAME", "second")
    monkeypatch.setenv("CODEX_HOME", "/home/ok/.codex-2")
    second = plan_pause.register_worker("plans-second@yoga")
    return main, second


def test_one_paused_account_stops_no_worker_and_every_one_paused_stops_them_all(control, workers):
    plan_pause.pause("codex", ".codex-2", note="refused until Friday")

    assert PlanAccountPause.objects.get().account == ".codex-2"
    # the other accounts take its calls, so both workers keep taking jobs
    assert control == [("go", ("plans-main@yoga",)), ("go", ("plans-second@yoga",))]

    control.clear()
    plan_pause.pause_all()
    assert control == [("stop", ("plans-main@yoga",)), ("stop", ("plans-second@yoga",))]

    control.clear()
    plan_pause.resume_all()
    assert not PlanAccountPause.objects.exists()
    assert control == [("go", ("plans-main@yoga",)), ("go", ("plans-second@yoga",))]


def test_a_worker_that_starts_with_every_account_paused_stands_still(workers, monkeypatch, control):
    stopped = []
    consumer = SimpleNamespace(cancel_task_queue=lambda queue: stopped.append(queue))
    monkeypatch.setenv("PLAN_WORKER_NAME", "second")
    monkeypatch.setenv("CODEX_HOME", "/home/ok/.codex-2")

    PlanAccountPause.objects.create(provider="codex", account=".codex-2")
    assert plan_pause.stop_if_paused(consumer, "plans-second@yoga") is False

    plan_pause.pause_all()
    assert plan_pause.stop_if_paused(consumer, "plans-second@yoga") is True
    assert stopped == ["plans"]
    assert PlanWorker.objects.get(name="main").claude_account == ".claude-2"


def test_the_dashboard_shows_the_pause_and_offers_the_buttons(client, control, workers):
    client.force_login(get_user_model().objects.create_user(username="staff", is_staff=True))
    PlanMeterReading.objects.create(provider="codex", account=".codex", week_percent=31)
    PlanMeterReading.objects.create(provider="codex", account=".codex-2", week_percent=40)
    PlanMeterReading.objects.create(provider="claude-code", account=".claude-2", week_percent=3)

    response = client.post(
        reverse("catalog:plan-account-pause"),
        {"action": "pause", "provider": "codex", "account": ".codex-2"},
    )
    assert response.status_code == 302

    meters = {m.account: m for m in plan_meters()}
    assert meters[".codex-2"].paused and not meters[".codex"].paused
    page = client.get(reverse("catalog:dashboard")).content.decode()
    assert "Codex-2" in page and "Claude-2" in page
    assert page.count('value="pause"') == 2 and page.count('value="resume"') == 1
    assert 'value="pause-all"' in page and 'value="resume-all"' in page

    client.post(reverse("catalog:plan-account-pause"), {"action": "resume-all"})
    assert not PlanAccountPause.objects.exists()


def test_an_account_pauses_itself_when_its_week_crosses_its_limit(control, workers):
    plan_pause.set_limit("codex", ".codex-2", "85")
    PlanMeterReading.objects.create(provider="codex", account=".codex-2", week_percent=80)

    assert plan_pause.pause_on_limit("codex", ".codex-2", 84) is False
    assert plan_pause.pause_on_limit("codex", ".codex-2", 86) is True
    assert PlanAccountPause.objects.get().note == "Paused at 85% limit"
    meter = next(m for m in plan_meters() if m.account == ".codex-2")
    assert meter.paused_at_limit and meter.pause_at_percent == 85


def test_an_account_run_on_past_its_limit_keeps_running(control, workers):
    """The limit acts on a crossing; the owner's Run past it is not undone by the next reading."""

    plan_pause.set_limit("codex", ".codex-2", "85")
    PlanMeterReading.objects.create(provider="codex", account=".codex-2", week_percent=90)

    assert plan_pause.pause_on_limit("codex", ".codex-2", 92) is False
    assert not PlanAccountPause.objects.exists()

    # the week resets under the limit, and the next climb crosses it again
    PlanMeterReading.objects.create(provider="codex", account=".codex-2", week_percent=3)
    assert plan_pause.pause_on_limit("codex", ".codex-2", 85) is True


def test_no_limit_never_pauses_and_a_manual_pause_keeps_its_note(control, workers):
    PlanMeterReading.objects.create(provider="codex", account=".codex", week_percent=10)
    assert plan_pause.pause_on_limit("codex", ".codex", 100) is False

    plan_pause.set_limit("codex", ".codex", "50")
    plan_pause.pause("codex", ".codex", note="Paused by staff")
    assert plan_pause.pause_on_limit("codex", ".codex", 60) is False
    assert PlanAccountPause.objects.get().note == "Paused by staff"


def test_the_limit_is_saved_from_the_row_and_cleared_when_empty(client, control, workers):
    from almonium_book_processor.catalog.models import PlanAccount

    client.force_login(get_user_model().objects.create_user(username="staff", is_staff=True))
    PlanMeterReading.objects.create(provider="codex", account=".codex-2", week_percent=52)
    url = reverse("catalog:plan-account-pause")
    row = {"provider": "codex", "account": ".codex-2"}

    response = client.post(url, {**row, "action": "limit", "pause_at": "85"})
    assert response.url.endswith("#plans")
    assert PlanAccount.objects.get(account=".codex-2").pause_at_percent == 85
    assert not PlanAccountPause.objects.exists()
    page = client.get(reverse("catalog:dashboard")).content.decode()
    assert "Auto-pauses at 85%" in page and 'class="plan-meter-limit" style="left:85%"' in page

    # the toggle carries the field too
    client.post(url, {**row, "action": "pause", "pause_at": ""})
    assert PlanAccount.objects.get(account=".codex-2").pause_at_percent is None
    assert PlanAccountPause.objects.exists()

    client.post(url, {**row, "action": "limit", "pause_at": "140"})
    assert PlanAccount.objects.get(account=".codex-2").pause_at_percent is None


def test_claude_calls_go_to_the_open_accounts_in_order(settings):
    settings.CLAUDE_CONFIG_DIRS = ["/home/ok/.claude-2", "/home/ok/.claude"]

    assert [p.name for p in plan_pause.open_claude_accounts()] == [".claude-2", ".claude"]
    PlanAccountPause.objects.create(provider="claude-code", account=".claude-2")
    assert [p.name for p in plan_pause.open_claude_accounts()] == [".claude"]
    PlanAccountPause.objects.create(provider="claude-code", account=".claude")
    assert plan_pause.open_claude_accounts() == []


def test_codex_calls_go_to_the_open_accounts_in_order(settings):
    settings.CODEX_HOMES = ["/home/ok/.codex", "/home/ok/.codex-2"]

    assert [p.name for p in plan_pause.open_codex_accounts()] == [".codex", ".codex-2"]
    PlanAccountPause.objects.create(provider="codex", account=".codex")
    assert [p.name for p in plan_pause.open_codex_accounts()] == [".codex-2"]


def test_calls_spend_the_account_put_first_on_the_dashboard(settings):
    settings.CLAUDE_CONFIG_DIRS = ["/home/ok/.claude-2", "/home/ok/.claude"]
    plan_pause.seed_priorities("claude-code", [".claude-2", ".claude"])
    assert [p.name for p in plan_pause.open_claude_accounts()] == [".claude-2", ".claude"]

    plan_pause.put_first("claude-code", ".claude", [".claude-2", ".claude"])

    assert [p.name for p in plan_pause.open_claude_accounts()] == [".claude", ".claude-2"]
    # the settings' order does not take the dashboard's back at the next meter reading
    plan_pause.seed_priorities("claude-code", [".claude-2", ".claude"])
    assert [p.name for p in plan_pause.open_claude_accounts()] == [".claude", ".claude-2"]
    # a paused first account hands its calls to the next
    plan_pause.pause("claude-code", ".claude")
    assert [p.name for p in plan_pause.open_claude_accounts()] == [".claude-2"]


def test_a_balanced_plan_calls_the_account_with_the_least_of_its_week_used(settings):
    from almonium_book_processor.catalog.models import PlanRouting

    settings.CODEX_HOMES = ["/home/ok/.codex", "/home/ok/.codex-2", "/home/ok/.codex-3"]
    PlanMeterReading.objects.create(provider="codex", account=".codex", week_percent=60)
    PlanMeterReading.objects.create(provider="codex", account=".codex-2", week_percent=20)
    plan_pause.set_mode("codex", PlanRouting.Mode.BALANCED)

    # an account never read goes last
    assert [p.name for p in plan_pause.open_codex_accounts()] == [".codex-2", ".codex", ".codex-3"]
    PlanMeterReading.objects.create(provider="codex", account=".codex-2", week_percent=70)
    assert [p.name for p in plan_pause.open_codex_accounts()] == [".codex", ".codex-2", ".codex-3"]

    plan_pause.set_mode("codex", PlanRouting.Mode.ORDER)
    assert [p.name for p in plan_pause.open_codex_accounts()] == [".codex", ".codex-2", ".codex-3"]
    with pytest.raises(ValueError):
        plan_pause.set_mode("codex", "random")


def test_the_dashboard_sets_the_mode_and_the_first_account(client, control, workers):
    from almonium_book_processor.catalog.models import PlanAccount, PlanRouting

    for account, used in ((".claude", 18), (".claude-2", 4)):
        PlanMeterReading.objects.create(provider="claude-code", account=account, week_percent=used)
    plan_pause.seed_priorities("claude-code", [".claude-2", ".claude"])
    client.force_login(get_user_model().objects.create_user("staff", is_staff=True))
    page = client.get(reverse("catalog:dashboard")).content.decode()
    assert "Spending order" in page and "Spend first" in page

    client.post(
        reverse("catalog:plan-routing"),
        {"provider": "claude-code", "action": "first", "account": ".claude"},
    )
    assert PlanAccount.objects.get(provider="claude-code", account=".claude").priority == 1
    assert PlanAccount.objects.get(provider="claude-code", account=".claude-2").priority == 2

    client.post(
        reverse("catalog:plan-routing"),
        {"provider": "claude-code", "action": "mode", "mode": "balanced"},
    )
    assert PlanRouting.objects.get(provider="claude-code").mode == "balanced"
    assert "next call" in client.get(reverse("catalog:dashboard")).content.decode()
