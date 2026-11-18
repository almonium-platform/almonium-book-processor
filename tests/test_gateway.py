from __future__ import annotations

import re
from decimal import Decimal
from pathlib import Path

import pytest

from almonium_book_processor.ai import gateway
from almonium_book_processor.ai.seats import Seat

SOURCE = Path(__file__).resolve().parents[1] / "src" / "almonium_book_processor"


def test_a_bare_model_runs_on_the_plan_that_serves_it_where_that_plan_is_here():
    plans = "codex,claude-code"
    assert gateway.route("gpt-5.6-terra", plans=plans) == Seat("codex", "gpt-5.6-terra")
    assert gateway.route("gpt-5.6-luna:high", plans=plans) == Seat("codex", "gpt-5.6-luna", "high")
    assert gateway.route("claude-opus-5-5", plans=plans) == Seat("claude-code", "claude-opus-5-5")


def test_a_bare_model_runs_on_the_api_where_its_plan_is_not_here():
    # a deployed environment names no plans: everything stays where it was
    assert gateway.route("gpt-5.6-terra", plans="") == Seat("openai", "gpt-5.6-terra")
    assert gateway.route("gpt-5.6-terra", plans="claude-code") == Seat("openai", "gpt-5.6-terra")


def test_a_model_with_no_price_never_goes_to_a_plan():
    # a plan call is recorded at its share of the list price; with none it would look free
    assert gateway.route("gpt-9-nova", plans="codex") == Seat("openai", "gpt-9-nova")


def test_a_seat_is_used_as_written_whatever_plans_are_here():
    assert gateway.route("openai:gpt-5.6-terra", plans="codex") == Seat("openai", "gpt-5.6-terra")
    assert gateway.route("codex:gpt-6-astra:medium", plans="") == Seat(
        "codex", "gpt-6-astra", "medium"
    )


def test_a_malformed_setting_is_refused():
    with pytest.raises(ValueError, match="effort"):
        gateway.route("gpt-5.6-terra:extreme", plans="codex")
    with pytest.raises(ValueError, match="names a model"):
        gateway.route(":high", plans="codex")


def test_on_plan_reads_lists_of_models_and_seats():
    assert gateway.on_plan("", "openai:x, gpt-5.6-terra", plans="codex")
    assert not gateway.on_plan("", "gpt-5.6-terra", plans="")


def test_only_the_api_batches():
    assert gateway.batches(Seat("openai", "gpt-5.6-terra"))
    assert not gateway.batches(Seat("codex", "gpt-5.6-terra"))


def test_unavailable_names_why_a_seat_cannot_be_called(settings):
    settings.OPENAI_API_KEY = ""
    settings.AI_PLANS = "codex"
    assert gateway.unavailable(Seat("openai", "gpt-5.6-terra"))
    assert gateway.unavailable(Seat("codex", "gpt-5.6-terra")) == ""
    assert "claude-code" in gateway.unavailable(Seat("claude-code", "claude-opus-5-5"))


def test_a_plan_call_costs_its_share_of_the_plan_and_an_api_call_its_table():
    tokens = {"input_tokens": 1_000_000, "cached_input_tokens": 0, "output_tokens": 0}
    table = {"input": "2.00", "cached_input": "0.20", "output": "12.00"}
    assert gateway.cost(Seat("openai", "gpt-5.6-terra"), api_table=table, **tokens) == 2
    assert gateway.cost(Seat("openai", "gpt-5.6-terra"), api_table=table, batch=True, **tokens) == 1
    # the Codex plan's measured share of the list price, 0.08
    assert gateway.cost(Seat("codex", "gpt-5.6-terra"), api_table=table, **tokens) == Decimal(
        "0.16"
    )


def test_a_refused_allowance_holds_a_direct_line_instead_of_failing_it():
    from almonium_book_processor.ai.cli_calls import AllowanceUsedUp

    class Refused:
        def respond(self, body):
            raise AllowanceUsedUp("used up")

    class Broken:
        def respond(self, body):
            raise RuntimeError("bad answer")

    with pytest.raises(AllowanceUsedUp):
        gateway.direct_line(Refused(), {"custom_id": "a", "body": {}})
    line = gateway.direct_line(Broken(), {"custom_id": "a", "body": {}})
    assert line["response"]["status_code"] == 502


# The gateway is the only place a provider is built: a step that built its own would never
# move when its setting does, which is how five steps were stuck on the API.
_BUILT = re.compile(r"\b(OpenAIBatchProvider|CodexProvider|ClaudeCodeProvider)\(")


def test_nothing_outside_the_ai_package_builds_a_provider():
    builders = [
        f"{path.relative_to(SOURCE)}:{number}"
        for path in SOURCE.rglob("*.py")
        if path.parent.name != "ai"
        for number, line in enumerate(path.read_text().splitlines(), 1)
        if _BUILT.search(line)
    ]
    assert builders == []
