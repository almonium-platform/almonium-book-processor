from __future__ import annotations

from decimal import Decimal

from almonium_book_processor.ai.pricing import PLAN_SHARE_OF_LIST, call_cost, has_price, list_cost

TOKENS = {"input_tokens": 1_000_000, "cached_input_tokens": 500_000, "output_tokens": 1_000_000}


def test_list_cost_prices_fresh_cached_and_output_tokens_apart():
    # half a million fresh at 10, half a million cached at 1, a million out at 50
    assert list_cost("gpt-6-astra", **TOKENS) == Decimal("55.5")


def test_an_api_call_costs_the_list_price():
    assert call_cost("openai", "gpt-6.1-sol", **TOKENS) == list_cost("gpt-6.1-sol", **TOKENS)


def test_a_plan_call_costs_the_share_of_the_plan_it_used_not_nothing():
    for provider in ("codex", "claude-code"):
        model = "gpt-6-astra" if provider == "codex" else "claude-opus-5-5"
        cost = call_cost(provider, model, **TOKENS)
        assert cost == (list_cost(model, **TOKENS) * PLAN_SHARE_OF_LIST[provider]).quantize(
            Decimal("0.000001")
        )
        assert 0 < cost < list_cost(model, **TOKENS)


def test_a_model_without_a_price_is_known_before_any_call():
    assert has_price("claude-opus-5-5")
    assert not has_price("gpt-9-nova")


def test_a_call_the_claude_cli_priced_costs_that_price_times_the_plans_share():
    from decimal import Decimal

    from almonium_book_processor.ai.pricing import PLAN_SHARE_OF_LIST, plan_priced

    computed = Decimal("0.010000")
    # the CLI's own list price of the call, cache writes and all, is what the meter saw
    priced = plan_priced({"claude_code": {"api_equivalent_cost_usd": 0.1}}, computed)
    assert priced == Decimal("0.1") * PLAN_SHARE_OF_LIST["claude-code"]
    # a call without the CLI's figure keeps the cost computed from its tokens
    assert plan_priced({"usage": {}}, computed) == computed
    assert plan_priced({"claude_code": {"api_equivalent_cost_usd": None}}, computed) == computed
