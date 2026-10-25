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


def test_pausing_an_account_stops_the_workers_on_it_and_resuming_starts_them(control, workers):
    plan_pause.pause("codex", ".codex-2", note="refused until Friday")

    assert PlanAccountPause.objects.get().account == ".codex-2"
    assert control == [("go", ("plans-main@yoga",)), ("stop", ("plans-second@yoga",))]

    control.clear()
    plan_pause.pause("claude-code", ".claude-2")
    # both workers share the Claude account, so both stand still
    assert control == [("stop", ("plans-main@yoga",)), ("stop", ("plans-second@yoga",))]

    control.clear()
    plan_pause.resume_all()
    assert not PlanAccountPause.objects.exists()
    assert control == [("go", ("plans-main@yoga",)), ("go", ("plans-second@yoga",))]


def test_a_worker_that_starts_on_a_paused_account_stands_still(workers, monkeypatch):
    PlanAccountPause.objects.create(provider="codex", account=".codex-2")
    stopped = []
    consumer = SimpleNamespace(cancel_task_queue=lambda queue: stopped.append(queue))

    monkeypatch.setenv("PLAN_WORKER_NAME", "second")
    monkeypatch.setenv("CODEX_HOME", "/home/ok/.codex-2")
    assert plan_pause.stop_if_paused(consumer, "plans-second@yoga") is True
    assert stopped == ["plans"]

    monkeypatch.setenv("PLAN_WORKER_NAME", "main")
    monkeypatch.setenv("CODEX_HOME", "/home/ok/.codex")
    assert plan_pause.stop_if_paused(consumer, "plans-main@yoga") is False
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
