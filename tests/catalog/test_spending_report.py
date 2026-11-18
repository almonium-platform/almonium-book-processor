"""The Spending page: each provider by day, week and month, all time, and what it went on."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from almonium_book_processor.catalog import spending_report
from almonium_book_processor.catalog.models import (
    AIRun,
    Edition,
    ModelConfiguration,
    PipelineRun,
    PromptTemplate,
    Work,
)

pytestmark = pytest.mark.django_db

NOW = datetime(2026, 11, 18, 15, 0, tzinfo=UTC)  # a Wednesday


@pytest.fixture
def ledger():
    work = Work.objects.create(slug="w", title="A book", author="Author")
    edition = Edition.objects.create(work=work, slug="w-en", language="en", status="ready")
    prompt = PromptTemplate.objects.create(
        name="p", version=1, purpose="p", system_prompt="s", user_template="u"
    )

    def call(provider, cost, at, purpose="literary_translation"):
        configuration, _ = ModelConfiguration.objects.get_or_create(
            name=f"{provider}-{purpose}",
            defaults={"provider": provider, "model": "m", "purpose": purpose},
        )
        run = AIRun.objects.create(
            edition=edition,
            model_configuration=configuration,
            prompt_template=prompt,
            idempotency_key=uuid.uuid4().hex,
            estimated_cost_usd=Decimal(cost),
            input_tokens=1000,
            output_tokens=500,
        )
        AIRun.objects.filter(pk=run.pk).update(created_at=at)

    def modal(usd, at):
        run = PipelineRun.objects.create(
            edition=edition,
            stage=PipelineRun.Stage.ALIGN,
            processor_version="offline-sentence",
            input_hash=uuid.uuid4().hex,
            idempotency_key=uuid.uuid4().hex,
            summary={"embedding": {"device": "modal", "modal_calls": 3, "usd": usd}},
        )
        PipelineRun.objects.filter(pk=run.pk).update(updated_at=at)

    return call, modal


def test_days_weeks_and_months_put_each_cost_in_its_own_bucket(ledger):
    call, modal = ledger
    call("openai", "1.00", NOW)
    call("openai", "0.50", NOW - timedelta(days=1))
    call("codex", "7.00", NOW - timedelta(days=2))  # Monday: still this week
    call("openai", "2.00", NOW - timedelta(days=3))  # Sunday: last week
    call("claude-code", "3.00", datetime(2026, 10, 30, tzinfo=UTC))  # last month
    modal("0.0400", NOW)

    days = spending_report.buckets("day", NOW)
    assert len(days) == 30 and days[-1].label == "18 Nov"
    assert days[-1].values["openai"] == Decimal("1.00")
    assert days[-1].values["modal"] == Decimal("0.04")
    assert days[-2].values["openai"] == Decimal("0.50")

    weeks = spending_report.buckets("week", NOW)
    assert len(weeks) == 12 and weeks[-1].start == datetime(2026, 11, 16, tzinfo=UTC)
    assert weeks[-1].billed == Decimal("1.54") and weeks[-1].plans == Decimal("7.00")
    assert weeks[-2].values["openai"] == Decimal("2.00")

    months = spending_report.buckets("month", NOW)
    assert [m.label for m in months[-2:]] == ["Oct 2026", "Nov 2026"]
    assert months[-1].billed == Decimal("3.54")
    assert months[-2].values["claude-code"] == Decimal("3.00")
    assert months[0].label == "Dec 2025"


def test_all_time_counts_every_month_not_only_this_one(ledger):
    call, modal = ledger
    call("openai", "1.00", NOW)
    call("openai", "9.00", datetime(2026, 8, 1, tzinfo=UTC))
    modal("0.5000", datetime(2026, 9, 1, tzinfo=UTC))
    spans = {span["name"]: span for span in spending_report.totals(NOW)}
    assert spans["All time"]["billed"] == "$10.50"
    assert spans["This month"]["billed"] == "$1.00"
    assert spans["Today"]["billed"] == "$1.00"


def test_the_chart_stacks_each_provider_in_its_own_colour_and_scales_to_the_peak(ledger):
    call, _ = ledger
    call("openai", "5.95", NOW)
    series = spending_report.buckets("day", NOW)
    chart = spending_report.chart(series, spending_report.BILLED)
    assert not chart["empty"]
    assert chart["ticks"][-1]["label"] == "$8.00"
    last = chart["columns"][-1]
    assert [s["provider"] for s in last["segments"]] == ["openai"]
    assert last["show_label"]
    assert chart["providers"] == [("openai", "OpenAI API", 1), ("modal", "Modal GPU", 2)]


def test_staff_see_the_page_and_save_caps_back_to_it(client, ledger):
    call, modal = ledger
    call("openai", "1.25", NOW)
    modal("0.0300", NOW)
    assert client.get(reverse("catalog:spending")).status_code == 302  # not staff
    staff = get_user_model().objects.create_user("staff", password="x", is_staff=True)
    client.force_login(staff)
    for by in ("day", "week", "month", "nonsense"):
        assert client.get(reverse("catalog:spending"), {"by": by}).status_code == 200
    page = client.get(reverse("catalog:spending")).content.decode()
    assert "What it went on" in page and "Sentence alignment embeddings" in page
    response = client.post(
        reverse("catalog:set-budgets"), {"cap-openai": "3", "return": "spending"}
    )
    assert response["Location"].endswith(reverse("catalog:spending") + "#caps")
