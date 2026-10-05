from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from almonium_book_processor.ai.claude_code_provider import ClaudeCodeProvider

BODY = {
    "model": "ignored-by-the-cli-provider",
    "instructions": "You are a translator.",
    "input": "Translate this chapter.",
    "reasoning": {"effort": "medium"},
    "text": {
        "format": {
            "type": "json_schema",
            "name": "chapter_translation",
            "schema": {
                "$schema": "https://json-schema.org/draft/2020-12/schema",
                "$defs": {"Block": {"type": "object"}},
                "type": "object",
                "properties": {"blocks": {"type": "array", "items": {"$ref": "#/$defs/Block"}}},
            },
        }
    },
}


def cli_result(**overrides):
    result = {
        "is_error": False,
        "session_id": "session-1",
        "structured_output": {"blocks": [{"block_id": "c1.p1", "text": "Привіт"}]},
        "duration_ms": 1200,
        "total_cost_usd": 0.05,
        "usage": {
            "input_tokens": 2,
            "cache_read_input_tokens": 4000,
            "cache_creation_input_tokens": 100,
            "output_tokens": 700,
            "output_tokens_details": {"thinking_tokens": 300},
        },
    }
    result.update(overrides)
    return result


def provider_with(stdout="", returncode=0, stderr=""):
    calls = []

    def runner(command, **kwargs):
        calls.append((command, kwargs))
        return SimpleNamespace(returncode=returncode, stdout=stdout, stderr=stderr)

    provider = ClaudeCodeProvider(
        model="claude-opus-5-5",
        binary="claude",
        timeout_seconds=5,
        runner=runner,
        pause=lambda _: None,
    )
    return provider, calls


def test_respond_returns_a_responses_shaped_body():
    provider, calls = provider_with(stdout=json.dumps(cli_result()))

    body = provider.respond(BODY)

    text = body["output"][0]["content"][0]["text"]
    # jobs shaped for the API ask whether the answer is complete
    assert body["status"] == "completed"
    assert json.loads(text) == {"blocks": [{"block_id": "c1.p1", "text": "Привіт"}]}
    # cached tokens are counted inside input_tokens, as the Responses API does
    assert body["usage"] == {
        "input_tokens": 4102,
        "output_tokens": 700,
        "input_tokens_details": {"cached_tokens": 4000},
        "output_tokens_details": {"reasoning_tokens": 300},
    }
    assert body["model"] == "claude-opus-5-5"


def test_respond_runs_the_cli_without_tools_servers_or_project_context():
    provider, calls = provider_with(stdout=json.dumps(cli_result()))

    provider.respond(BODY)

    command, kwargs = calls[0]
    # the prompt travels on standard input, so its length is not bounded by an argument's
    assert command[:2] == ["claude", "-p"]
    assert "Translate this chapter." not in command
    assert kwargs["input"] == "Translate this chapter."
    assert command[command.index("--tools") + 1] == ""
    assert command[command.index("--system-prompt") + 1] == "You are a translator."
    assert command[command.index("--effort") + 1] == "medium"
    assert "--strict-mcp-config" in command
    assert kwargs["cwd"] == provider.workdir
    assert list(provider.workdir.iterdir()) == []


def test_schema_is_converted_to_the_shape_the_cli_validates():
    provider, calls = provider_with(stdout=json.dumps(cli_result()))

    provider.respond(BODY)

    command, _ = calls[0]
    schema = json.loads(command[command.index("--json-schema") + 1])
    assert "$schema" not in schema and "$defs" not in schema
    assert schema["definitions"] == {"Block": {"type": "object"}}
    assert schema["properties"]["blocks"]["items"] == {"$ref": "#/definitions/Block"}


@pytest.mark.parametrize(
    ("stdout", "returncode", "message"),
    [
        ("", 1, "exited with 1"),
        ("not json", 0, "not JSON"),
        (json.dumps(cli_result(is_error=True, result="rate limited")), 0, "reported an error"),
        (json.dumps(cli_result(structured_output=None)), 0, "no structured output"),
    ],
)
def test_failures_raise_so_the_chapter_is_recorded_as_failed(stdout, returncode, message):
    provider, _ = provider_with(stdout=stdout, returncode=returncode, stderr="boom")

    with pytest.raises(RuntimeError, match=message):
        provider.respond(BODY)


def test_a_request_without_a_schema_is_refused():
    provider, _ = provider_with(stdout=json.dumps(cli_result()))

    with pytest.raises(ValueError, match="JSON schema"):
        provider.respond({**BODY, "text": {}})


def test_there_is_no_batch_service():
    provider, _ = provider_with()

    with pytest.raises(NotImplementedError):
        provider.submit([], metadata={})


def test_a_call_that_fails_in_passing_is_tried_once_more():
    results = [
        SimpleNamespace(returncode=1, stdout="", stderr="connection reset"),
        SimpleNamespace(returncode=0, stdout=json.dumps(cli_result()), stderr=""),
    ]
    pauses = []
    provider = ClaudeCodeProvider(
        model="claude-opus-5-5",
        binary="claude",
        timeout_seconds=5,
        runner=lambda command, **kwargs: results.pop(0),
        pause=pauses.append,
    )

    assert provider.respond(BODY)["status"] == "completed"
    assert results == [] and len(pauses) == 1
