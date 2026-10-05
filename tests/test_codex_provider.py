from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from almonium_book_processor.ai.codex_provider import CodexProvider, codex_meter

BODY = {
    "model": "gpt-6.1-sol",
    "instructions": "You are an editor.",
    "input": '{"blocks": []}',
    "reasoning": {"effort": "high"},
    "text": {"format": {"type": "json_schema", "name": "review", "schema": {"type": "object"}}},
}


def events(*items):
    return "\n".join(json.dumps(item) for item in items)


def answer(text='{"issues": [], "assessment": "ok"}'):
    return events(
        {"type": "thread.started"},
        {"type": "item.completed", "item": {"type": "agent_message", "text": text}},
        {
            "type": "turn.completed",
            "usage": {
                "input_tokens": 15000,
                "cached_input_tokens": 12000,
                "output_tokens": 900,
                "reasoning_output_tokens": 300,
            },
        },
    )


def provider_with(stdout="", stderr=""):
    calls = []

    def runner(command, **kwargs):
        schema_path = Path(command[command.index("--output-schema") + 1])
        calls.append((command, kwargs, json.loads(schema_path.read_text())))
        return SimpleNamespace(returncode=0, stdout=stdout, stderr=stderr)

    provider = CodexProvider(binary="codex", timeout_seconds=5, runner=runner, pause=lambda _: None)
    return provider, calls


def test_respond_returns_a_responses_shaped_body():
    provider, _ = provider_with(stdout=answer())

    body = provider.respond(BODY)

    assert json.loads(body["output"][0]["content"][0]["text"]) == {"issues": [], "assessment": "ok"}
    assert body["status"] == "completed"
    assert body["usage"] == {
        "input_tokens": 15000,
        "output_tokens": 900,
        "input_tokens_details": {"cached_tokens": 12000},
        "output_tokens_details": {"reasoning_tokens": 300},
    }


def test_respond_runs_an_ephemeral_read_only_session_with_the_prompt_on_stdin():
    provider, calls = provider_with(stdout=answer())

    provider.respond(BODY)

    command, kwargs, schema = calls[0]
    assert command[:4] == ["codex", "exec", "-m", "gpt-6.1-sol"]
    assert "--ephemeral" in command and command[command.index("--sandbox") + 1] == "read-only"
    assert "mcp_servers={}" in command and "model_reasoning_effort=high" in command
    # the prompt is read from standard input, and the schema file is gone afterwards
    assert command[-1] == "-"
    assert kwargs["input"].startswith("You are an editor.") and '{"blocks": []}' in kwargs["input"]
    assert schema == {"type": "object"}
    assert not Path(command[command.index("--output-schema") + 1]).exists()
    assert kwargs["cwd"] == provider.workdir


@pytest.mark.parametrize(
    ("stdout", "message"),
    [
        (events({"type": "error", "message": "You have hit your usage limit."}), "usage limit"),
        (answer(text="not json"), "not JSON"),
        ("", "no answer"),
    ],
)
def test_failures_raise_so_the_step_is_recorded_as_failed(stdout, message):
    provider, _ = provider_with(stdout=stdout)

    with pytest.raises(RuntimeError, match=message):
        provider.respond(BODY)


def test_a_request_without_a_schema_is_refused():
    provider, _ = provider_with(stdout=answer())

    with pytest.raises(ValueError, match="JSON schema"):
        provider.respond({**BODY, "text": {}})


def test_the_meter_is_read_from_the_newest_session_log(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    day = tmp_path / ".codex" / "sessions" / "2026" / "10" / "04"
    day.mkdir(parents=True)
    limits = {
        "rate_limits": {
            "primary": {"used_percent": 14.0, "window_minutes": 10080, "resets_at": 1791734040},
            "secondary": None,
            "plan_type": "prolite",
        }
    }
    commands = []

    def runner(command, **kwargs):
        commands.append(command)
        (day / "rollout-2026-10-04T21-00-00-x.jsonl").write_text(json.dumps(limits) + "\n")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    meter = codex_meter(binary="codex", runner=runner)

    assert meter == {
        "used_percent": 14.0,
        "window_minutes": 10080,
        "resets_at": 1791734040,
        "plan_type": "prolite",
    }
    # the call must leave a session log, so it is the one call that is not ephemeral
    assert "--ephemeral" not in commands[0]


def test_an_unreadable_meter_is_none_and_never_an_error(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    assert codex_meter(binary="codex", runner=lambda *a, **k: None) is None


def test_a_call_that_fails_in_passing_is_tried_once_more():
    outputs = ["", answer()]
    pauses = []
    provider = CodexProvider(
        binary="codex",
        timeout_seconds=5,
        runner=lambda command, **kwargs: SimpleNamespace(
            returncode=0, stdout=outputs.pop(0), stderr=""
        ),
        pause=pauses.append,
    )

    assert provider.respond(BODY)["status"] == "completed"
    assert outputs == [] and len(pauses) == 1


def test_a_timeout_is_tried_once_more_and_then_raised():
    import subprocess

    calls = []

    def runner(command, **kwargs):
        calls.append(command)
        raise subprocess.TimeoutExpired(command, 5)

    provider = CodexProvider(binary="codex", timeout_seconds=5, runner=runner, pause=lambda _: None)

    with pytest.raises(subprocess.TimeoutExpired):
        provider.respond(BODY)
    assert len(calls) == 2


def test_a_plan_whose_allowance_is_used_up_is_not_asked_again():
    provider, calls = provider_with(
        stdout=events({"type": "error", "message": "You have hit your usage limit."})
    )

    with pytest.raises(RuntimeError, match="usage limit"):
        provider.respond(BODY)
    assert len(calls) == 1


def test_an_answer_that_breaks_the_schema_is_asked_for_again_and_never_quoted():
    schema = {
        "type": "object",
        "properties": {"quote": {"type": "string", "maxLength": 5}},
        "required": ["quote"],
    }
    body = {**BODY, "text": {"format": {"type": "json_schema", "name": "x", "schema": schema}}}
    outputs = [answer(text='{"quote": "a secret sentence"}'), answer(text='{"quote": "short"}')]
    provider = CodexProvider(
        binary="codex",
        timeout_seconds=5,
        runner=lambda command, **kwargs: SimpleNamespace(
            returncode=0, stdout=outputs.pop(0), stderr=""
        ),
        pause=lambda _: None,
    )

    assert provider.respond(body)["status"] == "completed"
    assert outputs == []

    always_long, _ = provider_with(stdout=answer(text='{"quote": "a secret sentence"}'))
    with pytest.raises(RuntimeError, match=r"quote \(maxLength\)") as failure:
        always_long.respond(body)
    assert "secret" not in str(failure.value)
