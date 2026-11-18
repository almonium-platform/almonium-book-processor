"""The one way into a model: which provider runs a step's model here, and the caller for it.

Every step names its model in a setting, written one of two ways:

    gpt-5.6-terra              the model alone: on the owner's plan that serves it, where this
    gpt-5.6-terra:high         environment has that plan, else on the metered API
    openai:gpt-5.6-terra       a seat (ai/seats.py): the provider is named and always used
    codex:gpt-6-astra:medium

Which plans an environment has is ``AI_PLANS``: the owner's machine names codex and
claude-code, whose CLIs are signed in there; a deployed environment names none, so every bare
model runs on the API there exactly as before. A plan is a flat fee, its calls a small share of
the API's price, so a bare model goes to a plan whenever one serves it. A plan has no Batch
service: a step that batches on the API makes the same requests one by one on a plan.

Nothing outside this package builds a provider; every call comes through ``provider`` (or
``batch`` for the Batch service's own operations), so moving a step to another provider is a
setting, never code. ``tests/test_gateway.py`` holds that line.
"""

from __future__ import annotations

from almonium_book_processor.ai.pricing import has_price
from almonium_book_processor.ai.seats import EFFORTS, PROVIDERS, Seat, parse_seat

# Which plan serves a vendor's models: the Codex CLI runs OpenAI's, Claude Code Anthropic's.
_PLAN_BY_PREFIX = (("gpt-", "codex"), ("claude-", "claude-code"))


def plan_for(model: str) -> str | None:
    """The plan whose CLI serves this model, if any does."""

    return next((plan for prefix, plan in _PLAN_BY_PREFIX if model.startswith(prefix)), None)


def plans_here(plans: str | None = None) -> set[str]:
    """The plans this environment can call (``AI_PLANS``)."""

    if plans is None:
        from django.conf import settings

        plans = settings.AI_PLANS
    return {plan.strip() for plan in plans.split(",") if plan.strip()}


def route(setting: str, *, plans: str | None = None) -> Seat:
    """Who runs a step here: a seat as written, or a bare model on a plan that serves it.

    ``plans`` is ``AI_PLANS`` as written, for callers (the settings module) that run before
    Django's settings exist.
    """

    setting = setting.strip()
    if setting.partition(":")[0] in PROVIDERS:
        return parse_seat(setting)
    model, _, effort = setting.partition(":")
    if not model:
        raise ValueError("A step names a model, or a seat <provider>:<model>[:<effort>]")
    if effort and effort not in EFFORTS:
        raise ValueError(f"A step's effort is {', '.join(EFFORTS)}, not {effort!r}")
    plan = plan_for(model)
    # a plan model must have a price, or its calls would be recorded free; an unpriced model
    # stays on the API, which reports what it cost
    if plan in plans_here(plans) and has_price(model):
        return Seat(plan, model, effort)
    return Seat("openai", model, effort)


def on_plan(*settings_values: str, plans: str | None = None) -> bool:
    """Whether any of these settings (each one model or seat, or several by commas) is a plan."""

    return any(
        route(value, plans=plans).on_plan
        for setting in settings_values
        for value in setting.split(",")
        if value.strip()
    )


def unavailable(seat: Seat) -> str:
    """Why this seat cannot be called here, or "" when it can."""

    from django.conf import settings

    if seat.provider == "openai":
        return "" if settings.OPENAI_API_KEY else "Configure an OpenAI key to call the API."
    if seat.provider in plans_here():
        return ""
    return f"The {seat.provider} plan is not signed in here (AI_PLANS)."


def provider(seat: Seat):
    """The caller for a seat. Every one answers ``respond(body)`` with a Responses-shaped body
    and checks the owner's monthly cap for its provider first (catalog/budgets.py)."""

    # imported here: the CLI providers read settings when they are built
    if seat.provider == "claude-code":
        from almonium_book_processor.ai.claude_code_provider import ClaudeCodeProvider
        from almonium_book_processor.catalog.plan_pause import open_claude_accounts

        return ClaudeCodeProvider(model=seat.model, accounts=open_claude_accounts)
    if seat.provider == "codex":
        from almonium_book_processor.ai.codex_provider import CodexProvider
        from almonium_book_processor.catalog.plan_pause import open_codex_accounts

        return CodexProvider(accounts=open_codex_accounts)
    return batch()


def batch():
    """The API's Batch service, for what only it does: submit, retrieve, cancel, read output."""

    from almonium_book_processor.ai.openai_provider import OpenAIBatchProvider

    return OpenAIBatchProvider()


def batches(seat: Seat) -> bool:
    """Whether a step that can batch does so on this seat: only the API has a Batch service."""

    return seat.provider == "openai"


def prices(seat: Seat, api_table: dict[str, str] | None = None) -> dict[str, str]:
    """A seat's price per million tokens: on a plan the share of the plan the list price
    uses up; on the API the step's own table where it keeps one, else the list price."""

    from almonium_book_processor.ai.pricing import seat_prices

    if seat.provider == "openai" and api_table is not None:
        return api_table
    return seat_prices(seat.provider, seat.model)


def cost(
    seat: Seat,
    *,
    input_tokens: int,
    cached_input_tokens: int,
    output_tokens: int,
    api_table: dict[str, str] | None = None,
    batch: bool = False,
    response: dict | None = None,
):
    """What a call cost the owner: on a plan its share of the plan, the CLI's own figure where
    it gives one; on the API the step's table (or the list price), halved through Batch."""

    from decimal import Decimal

    from almonium_book_processor.ai.pricing import MILLION, call_cost, plan_priced

    if seat.on_plan:
        computed = call_cost(
            seat.provider,
            seat.model,
            input_tokens=input_tokens,
            cached_input_tokens=cached_input_tokens,
            output_tokens=output_tokens,
        )
        return plan_priced(response or {}, computed)
    table = api_table or prices(seat)
    standard = (
        Decimal(max(0, input_tokens - cached_input_tokens)) * Decimal(table["input"])
        + Decimal(cached_input_tokens) * Decimal(table["cached_input"])
        + Decimal(output_tokens) * Decimal(table["output"])
    ) / MILLION
    return standard * Decimal("0.5") if batch else standard


def direct_line(caller, request: dict) -> dict:
    """One Batch-shaped request answered directly, as a Batch output line.

    A call that failed is a failed line, with what it was paid for; an allowance or cap that
    refused, or a network that is down, is no answer at all and is raised, so the run holds.
    """

    from almonium_book_processor.ai.cli_calls import AllowanceUsedUp, NetworkDown, spent_by

    try:
        body = caller.respond(request["body"])
    except (AllowanceUsedUp, NetworkDown):
        raise
    except Exception as error:
        # a CLI call that failed after the model answered was paid for all the same
        spent = (spent_by(error) or {}).get("usage") or {}
        return {
            "custom_id": request["custom_id"],
            "response": {"status_code": 502, "body": {"error": str(error)[:500], "usage": spent}},
        }
    return {"custom_id": request["custom_id"], "response": {"status_code": 200, "body": body}}
