from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from almonium_book_processor.ai.codex_provider import CodexProvider

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

    return CodexProvider(binary="codex", timeout_seconds=5, runner=runner), calls


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
