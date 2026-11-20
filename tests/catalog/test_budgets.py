"""Monthly caps per provider: what each has cost, and a cap that holds instead of failing."""

from __future__ import annotations

import json
import uuid
from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from almonium_book_processor.ai.claude_code_provider import ClaudeCodeProvider
from almonium_book_processor.ai.cli_calls import (
    BUDGET_REACHED,
    AllowanceUsedUp,
    BudgetReached,
    recorded_error,
)
from almonium_book_processor.ai.openai_provider import OpenAIBatchProvider
from almonium_book_processor.catalog import budgets, production
from almonium_book_processor.catalog.models import (
    AIRun,
    Edition,
    ModelConfiguration,
    PipelineRun,
    PromptTemplate,
    ProviderBudget,
    Work,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def ledger():
    work = Work.objects.create(slug="w", title="A book", author="Author")
    edition = Edition.objects.create(work=work, slug="w-en", language="en", status="ready")
    prompt = PromptTemplate.objects.create(
        name="p", version=1, purpose="p", system_prompt="s", user_template="u"
    )

    def call(provider, cost, *, days_ago=0):
        configuration, _ = ModelConfiguration.objects.get_or_create(
            name=f"{provider}-model",
            defaults={"provider": provider, "model": "m", "purpose": "p"},
        )
        run = AIRun.objects.create(
            edition=edition,
            model_configuration=configuration,
            prompt_template=prompt,
            idempotency_key=uuid.uuid4().hex,
            status=AIRun.Status.SUCCEEDED,
            estimated_cost_usd=Decimal(cost),
        )
        if days_ago:
            AIRun.objects.filter(pk=run.pk).update(
                created_at=budgets.month_start() - timedelta(days=days_ago)
            )
        return run

    def modal(usd):
        return PipelineRun.objects.create(
            edition=edition,
            stage=PipelineRun.Stage.ALIGN,
            processor_version="offline-sentence",
            input_hash=uuid.uuid4().hex,
            idempotency_key=uuid.uuid4().hex,
            summary={"embedding": {"device": "modal", "modal_calls": 2, "usd": usd}},
        )

    return call, modal


def test_each_provider_costs_what_its_calls_cost_this_month(ledger):
    call, modal = ledger
    call("openai", "1.50")
    call("openai", "0.25")
    call("openai", "9.00", days_ago=3)  # last month
    call("codex", "4.00")
    modal("0.0300")
    lines = {line.provider: line for line in budgets.overview()}
    assert lines["openai"].spent == Decimal("1.75")
    assert lines["codex"].spent == Decimal("4.00")
    assert lines["claude-code"].spent == Decimal("0")
    assert lines["modal"].spent == Decimal("0.03")
    # money first, then the plans
    assert [line.metered for line in budgets.overview()] == [True, True, False, False, False]
    assert lines["antigravity"].name == "Gemini plan" and lines["antigravity"].spent == Decimal("0")


def test_no_cap_allows_anything_and_modal_defaults_to_the_free_credits(ledger, settings):
    settings.MODAL_MONTHLY_BUDGET_USD = 25
    assert budgets.cap("openai") is None
    budgets.check("openai", Decimal("1000"))
    assert str(budgets.cap("modal")) == "25.00"
    # a row without an amount lifts even Modal's default
    budgets.set_caps({"modal": None})
    assert budgets.cap("modal") is None


def test_a_spent_cap_refuses_with_a_reason_that_holds_and_does_not_fail(ledger):
    call, _ = ledger
    call("openai", "2.00")
    budgets.set_caps({"openai": Decimal("2.00")})
    with pytest.raises(BudgetReached) as refused:
        budgets.check("openai")
    error = refused.value
    # an AllowanceUsedUp: every job records it whole and every production waits on it
    assert isinstance(error, AllowanceUsedUp)
    assert str(error).startswith(f"{BUDGET_REACHED}: OpenAI API has cost $2.00 of its $2.00")
    assert "Raise the cap on the dashboard" in str(error)
    assert recorded_error(error) == str(error)
    assert BUDGET_REACHED in production.REFUSALS
    assert BUDGET_REACHED in production.PROVIDER_HOLDS
    assert BUDGET_REACHED in production.CIRCUMSTANTIAL_HOLDS
    # raising it lets the next call through
    budgets.set_caps({"openai": Decimal("5")})
    budgets.check("openai")


def test_an_estimate_that_would_pass_the_cap_is_refused_before_it_is_spent(ledger):
    call, _ = ledger
    call("openai", "4.00")
    budgets.set_caps({"openai": Decimal("5")})
    assert budgets.allows("openai", Decimal("0.99"))
    assert not budgets.allows("openai", Decimal("1.01"))


def test_the_openai_adapter_refuses_before_the_request_leaves(ledger):
    call, _ = ledger
    call("openai", "3.00")
    budgets.set_caps({"openai": Decimal("3")})
    sent = []
    provider = object.__new__(OpenAIBatchProvider)
    provider.client = SimpleNamespace(
        with_options=lambda **_: SimpleNamespace(
            responses=SimpleNamespace(create=lambda **body: sent.append(body))
        ),
        files=SimpleNamespace(create=lambda **_: sent.append("file")),
    )
    with pytest.raises(BudgetReached):
        provider.respond({"model": "m"})
    with pytest.raises(BudgetReached):
        provider.submit([{"body": 1}], metadata={})
    assert sent == []


def test_a_plan_adapter_refuses_before_any_account_is_asked(ledger):
    call, _ = ledger
    call("claude-code", "10.00")
    budgets.set_caps({"claude-code": Decimal("10")})
    asked = []
    provider = ClaudeCodeProvider(
        model="claude-opus-5-5",
        binary="claude",
        timeout_seconds=5,
        runner=lambda *a, **k: asked.append(a),
        pause=lambda _: None,
    )
    body = {"text": {"format": {"schema": {"type": "object"}}}, "input": "x"}
    with pytest.raises(BudgetReached):
        provider.respond(body)
    assert asked == []
    assert json.dumps(body)  # untouched


def test_staff_set_caps_on_the_dashboard_and_see_each_providers_month(client, ledger):
    call, _ = ledger
    call("openai", "1.25")
    staff = get_user_model().objects.create_user("staff", password="x", is_staff=True)
    client.force_login(staff)
    response = client.post(
        reverse("catalog:set-budgets"),
        {"cap-openai": "1.00", "cap-modal": "25", "cap-codex": "", "cap-claude-code": ""},
    )
    assert response.status_code == 302
    assert ProviderBudget.objects.get(provider="openai").monthly_usd == Decimal("1.00")
    assert ProviderBudget.objects.get(provider="codex").monthly_usd is None
    page = client.get(reverse("catalog:dashboard")).content.decode()
    assert "Spending ·" in page
    assert "OpenAI API $1.25 of $1.00" in page
    assert "Cap reached · OpenAI API" in page


def test_a_cap_must_be_dollars(client, ledger):
    staff = get_user_model().objects.create_user("staff", password="x", is_staff=True)
    client.force_login(staff)
    client.post(reverse("catalog:set-budgets"), {"cap-openai": "-3"})
    client.post(reverse("catalog:set-budgets"), {"cap-openai": "lots"})
    assert not ProviderBudget.objects.exists()
