"""What a model call cost, whether it was metered or ran on a flat-rate plan.

A call through the API costs its tokens at the list price. A call through the Claude Code or
Codex CLI runs on a plan the owner pays for by the month, and it is not free: it uses up part of
a weekly allowance that was paid for. Its cost is that share of the plan's price.

The share is measured, not published. The Codex CLI records the plan's weekly meter, in whole
percent, in its session log; reading it before and after runs of known token counts gives the
plan dollars that one list-price dollar of tokens consumed. The figures below are from such
readings and are coarse, because the meter moves in whole points. ``plan_meter`` reads the meter,
and the plan commands store the readings around each run, so the figures can be kept current.
"""

from __future__ import annotations

from decimal import Decimal

MILLION = Decimal(1_000_000)

# USD per million tokens at list price on 2026-10-04: input, cached input, output. Cached input
# is a tenth of input at both vendors. The Claude models are named as the CLI names them.
LIST_PRICES = {
    "gpt-5.6-terra": ("2", "0.2", "12"),
    "gpt-5.6-luna": ("0.2", "0.02", "1.2"),
    "gpt-6-astra": ("10", "1", "50"),
    "gpt-6.1-sol": ("2", "0.2", "10"),
    "gpt-6-sol": ("2", "0.2", "10"),
    "fable": ("10", "1", "50"),
    "opus": ("4", "0.4", "20"),
    "sonnet": ("2", "0.2", "10"),
}

# A plan's price for one week, in USD: twelve monthly payments over fifty-two weeks.
PLAN_WEEK_USD = {
    "codex": Decimal(100) * 12 / 52,
    "claude-code": Decimal(200) * 12 / 52,
}

# Plan dollars consumed per list-price dollar of tokens, measured on 2026-10-04.
# codex, Pro $100: 15 meter points (USD 3.46 of the plan) for USD 43.8 of tokens at list price.
#   gpt-6-astra alone (entries, cross-checks, a whole book translated) came to 0.081 and a
#   review that was mostly gpt-6.1-sol to 0.077, so the meter follows the list price and one
#   figure serves every model.
# claude-code, Max $200: one meter point (USD 0.46) per about forty Opus dictionary entries,
#   which the CLI itself prices at USD 0.061 each. Measured once, on Opus only; the CLI
#   exposes no meter, so this one cannot be re-read in code, and Fable may be metered apart.
PLAN_SHARE_OF_LIST = {
    "codex": Decimal("0.08"),
    "claude-code": Decimal("0.19"),
}


def has_price(model: str) -> bool:
    return model in LIST_PRICES


def seat_prices(provider: str, model: str) -> dict[str, str]:
    """A seat's price table per million tokens, for stages that price a call from one.

    An API seat's is the list price; a plan seat's is the list price times the plan's share.
    """

    share = PLAN_SHARE_OF_LIST.get(provider, Decimal(1))
    fresh, cached, output = (Decimal(price) * share for price in LIST_PRICES[model])
    return {"input": str(fresh), "cached_input": str(cached), "output": str(output)}


def list_cost(
    model: str, *, input_tokens: int, cached_input_tokens: int, output_tokens: int
) -> Decimal:
    """The tokens at the provider's list price."""

    fresh, cached, output = (Decimal(price) for price in LIST_PRICES[model])
    return (
        Decimal(max(0, input_tokens - cached_input_tokens)) * fresh
        + Decimal(cached_input_tokens) * cached
        + Decimal(output_tokens) * output
    ) / MILLION


def call_cost(
    provider: str, model: str, *, input_tokens: int, cached_input_tokens: int, output_tokens: int
) -> Decimal:
    """What the call cost the owner: the list price, or the share of the plan it used up."""

    cost = list_cost(
        model,
        input_tokens=input_tokens,
        cached_input_tokens=cached_input_tokens,
        output_tokens=output_tokens,
    )
    return (cost * PLAN_SHARE_OF_LIST.get(provider, Decimal(1))).quantize(Decimal("0.000001"))
