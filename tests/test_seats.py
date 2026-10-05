from __future__ import annotations

import pytest

from almonium_book_processor.ai.claude_code_provider import ClaudeCodeProvider
from almonium_book_processor.ai.codex_provider import CodexProvider
from almonium_book_processor.ai.openai_provider import OpenAIBatchProvider
from almonium_book_processor.ai.seats import Seat, parse_seat, provider_for


def test_a_seat_names_provider_model_and_optionally_effort():
    assert parse_seat("codex:gpt-6-astra") == Seat("codex", "gpt-6-astra", "")
    assert parse_seat(" claude-code:opus:high ") == Seat("claude-code", "opus", "high")
    assert parse_seat("codex:gpt-6.1-sol:medium").on_plan
    assert not parse_seat("openai:gpt-5.6-terra").on_plan


@pytest.mark.parametrize(
    ("setting", "message"),
    [
        ("gemini:pro", "A seat is"),
        ("codex:", "A seat is"),
        ("codex:gpt-6-astra:extreme", "effort"),
        # a plan model must have a price before it is used, or its calls would be recorded free
        ("codex:gpt-9-nova", "No price"),
    ],
)
def test_a_malformed_seat_is_refused_before_any_call(setting, message):
    with pytest.raises(ValueError, match=message):
        parse_seat(setting)


def test_each_provider_gets_its_own_caller(settings):
    settings.OPENAI_API_KEY = "test-key"
    assert isinstance(provider_for("codex", "gpt-6-astra"), CodexProvider)
    assert isinstance(provider_for("openai", "gpt-5.6-terra"), OpenAIBatchProvider)
    claude = provider_for("claude-code", "fable")
    assert isinstance(claude, ClaudeCodeProvider) and claude.model == "fable"


def test_pages_name_a_claude_model_with_its_version_as_the_gpt_names_carry_theirs():
    from almonium_book_processor.ai.seats import versioned

    assert versioned("opus + gpt-6.1-sol") == "opus-5.5 + gpt-6.1-sol"
    assert versioned("fable and gpt-6-astra") == "fable-5.1 and gpt-6-astra"
    assert versioned("opus-5.5") == "opus-5.5"
