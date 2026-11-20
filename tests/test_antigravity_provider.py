from __future__ import annotations

import json
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from almonium_book_processor.ai import antigravity_provider, gateway
from almonium_book_processor.ai.antigravity_provider import AntigravityProvider, antigravity_meter
from almonium_book_processor.ai.cli_calls import AllowanceUsedUp, CallFailed
from almonium_book_processor.ai.seats import Seat, parse_seat

SCHEMA = {
    "type": "object",
    "required": ["title"],
    "additionalProperties": False,
    "properties": {"title": {"type": "string"}},
}
BODY = {
    "model": "gemini-4-carbon",
    "instructions": "Translate the title.",
    "input": "Alice",
    "reasoning": {"effort": "medium"},
    "text": {"format": {"schema": SCHEMA}},
}


def said(result: dict, stderr: str = ""):
    return SimpleNamespace(stdout="a notice\n" + json.dumps(result), stderr=stderr)


@pytest.fixture(autouse=True)
def no_cap(monkeypatch):
    from almonium_book_processor.catalog import budgets

    monkeypatch.setattr(budgets, "check", lambda provider: None)
    monkeypatch.setattr("almonium_book_processor.ai.cli_calls._resting_until", {})


def provider(runner):
    return AntigravityProvider(binary="agy", runner=runner, pause=lambda seconds: None)


def test_a_request_is_one_call_with_the_rules_before_the_material_and_the_shape_in_words():
    calls = []

    def runner(command, **kwargs):
        calls.append((command, kwargs))
        return said(
            {
                "status": "SUCCESS",
                "response": '```json\n{"title": "Аліса"}\n```',
                "usage": {
                    "input_tokens": 900,
                    "output_tokens": 20,
                    "thinking_tokens": 300,
                    "cache_read_tokens": 700,
                },
            }
        )

    body = provider(runner).respond(BODY)
    command, kwargs = calls[0]
    assert command[:2] == ["agy", "-p"]
    assert command[2].startswith("Translate the title.\n\nDo not run commands")
    assert "Alice" in command[2] and json.dumps(SCHEMA) in command[2]
    # the CLI names a model with its effort
    assert command[command.index("--model") + 1] == "gemini-4-carbon-medium"
    assert kwargs["cwd"].name == "almonium-antigravity-empty"
    assert json.loads(body["output"][0]["content"][0]["text"]) == {"title": "Аліса"}
    # thinking is charged as output
    assert body["usage"]["output_tokens"] == 320
    assert body["usage"]["input_tokens_details"]["cached_tokens"] == 700
    assert body["plan_account"] == antigravity_provider.ACCOUNT


def test_an_answer_that_does_not_fit_was_paid_for_and_is_not_an_answer():
    def runner(command, **kwargs):
        return said(
            {
                "status": "SUCCESS",
                "response": '{"name": "x"}',
                "usage": {"input_tokens": 10, "output_tokens": 5},
            }
        )

    with pytest.raises(CallFailed) as failure:
        provider(runner).respond(BODY)
    assert failure.value.spent["usage"]["input_tokens"] == 20  # tried twice, both paid


def test_a_used_up_plan_holds_the_work_instead_of_failing_it():
    def runner(command, **kwargs):
        return said({"status": "ERROR", "error": "You have exhausted your quota for Gemini models"})

    with pytest.raises(AllowanceUsedUp):
        provider(runner).respond(BODY)


def test_a_paused_account_is_not_asked():
    asked = []
    paused = AntigravityProvider(
        binary="agy", runner=lambda *a, **k: asked.append(a), accounts=lambda: []
    )
    with pytest.raises(AllowanceUsedUp, match="every Gemini account is paused"):
        paused.respond(BODY)
    assert not asked


def test_a_request_too_long_for_one_argument_is_refused_before_the_plan_is_asked():
    asked = []
    long = {**BODY, "input": "я" * 70_000}
    with pytest.raises(ValueError, match="bytes"):
        provider(lambda *a, **k: asked.append(a)).respond(long)
    assert not asked


def test_the_meter_is_what_is_used_of_the_gemini_models_week_and_session():
    def runner(command, **kwargs):
        assert command[1:] == ["-p", "/usage"]
        return SimpleNamespace(
            stdout=(
                "Gemini Models\tWeekly Limit Remaining\t93%\t2026-11-27T14:44:13Z\n"
                "Gemini Models\tFive Hour Limit Remaining\t60%\t2026-11-20T19:44:13Z\n"
                "Claude and GPT models\tWeekly Limit Remaining\t100%\t2026-11-27T14:53:37Z\n"
            ),
            stderr="",
        )

    meter = antigravity_meter(binary="agy", runner=runner)
    assert (meter["week_percent"], meter["session_percent"]) == (7, 40)
    assert meter["week_resets_at"] == datetime(2026, 11, 27, 14, 44, 13, tzinfo=UTC)
    assert antigravity_meter(binary="agy", runner=lambda *a, **k: 1 / 0) is None


def test_a_gemini_model_is_routed_to_googles_plan_and_never_to_openais_api(settings):
    assert gateway.route("gemini-4-carbon:medium", plans="codex,antigravity") == Seat(
        "antigravity", "gemini-4-carbon", "medium"
    )
    assert gateway.route("gemini-4-carbon", plans="codex").provider == "antigravity"
    assert parse_seat("antigravity:gemini-4-argon:high").on_plan
    settings.AI_PLANS = "codex"
    assert "not signed in" in gateway.unavailable(Seat("antigravity", "gemini-4-carbon"))
    settings.AI_PLANS = "codex,antigravity"
    assert gateway.unavailable(Seat("antigravity", "gemini-4-carbon")) == ""
    assert not gateway.batches(Seat("antigravity", "gemini-4-carbon"))


def test_a_lost_login_holds_the_work_and_is_not_counted_as_its_failure():
    asked = []

    def runner(command, **kwargs):
        asked.append(command)
        return SimpleNamespace(stdout="", stderr="error: authentication failed or timed out")

    with pytest.raises(AllowanceUsedUp, match="not signed in"):
        provider(runner).respond(BODY)
    assert len(asked) == 2  # once more after the pause, as any plan call; then held
