from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
import time
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

from django.conf import settings

from almonium_book_processor.ai.cli_calls import CallFailed, fits_schema, tried_twice

# The CLI writes every prompt to a one-hour cache and charges that write above the input
# price. A request here is one chapter under one prompt: almost nothing is ever read back
# (a tenth of the input on 102 audit calls), so the cache only costs. With it off the same
# Opus call came to USD 0.045 instead of USD 0.070.
UNCACHED = {**os.environ, "DISABLE_PROMPT_CACHING": "1"}

_METERS = {
    "session_percent": r"Current session: (\d+)% used",
    "week_percent": r"Current week \(all models\): (\d+)% used",
    "fable_week_percent": r"Current week \(Fable\): (\d+)% used",
}


def claude_config_dir(config_dir: str | Path | None = None) -> Path:
    """The directory that holds a Claude Code account: its login and settings.

    The CLI reads it from ``CLAUDE_CONFIG_DIR`` and falls back to ``~/.claude``, so a second
    account is a second directory, and a worker started with it set works on that account.
    """

    return Path(config_dir or os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude")


def claude_meter(
    *,
    config_dir: str | Path | None = None,
    binary: str | None = None,
    runner: Callable[..., Any] = subprocess.run,
) -> dict[str, int] | None:
    """An account's meters as the CLI's /usage screen shows them, or None when unreadable.

    Whole percent of the five-hour session, of the week for all models, and of the week for
    Fable, which is metered apart. Asking costs no tokens. The meters are the account's:
    every Claude Code session on it moves them, so a reading before and after a job
    measures that job only if nothing else ran.
    """

    workdir = Path(tempfile.gettempdir()) / "almonium-claude-code-empty"
    workdir.mkdir(parents=True, exist_ok=True)
    try:
        completed = runner(
            [
                binary or settings.CLAUDE_CODE_BINARY,
                "-p",
                "--output-format",
                "json",
                "--no-session-persistence",
                "--strict-mcp-config",
                "--mcp-config",
                '{"mcpServers": {}}',
            ],
            input="/usage",
            capture_output=True,
            text=True,
            timeout=120,
            cwd=workdir,
            env={**os.environ, "CLAUDE_CONFIG_DIR": str(claude_config_dir(config_dir))},
        )
        screen = json.loads(completed.stdout)["result"]
    except Exception:  # a meter that cannot be read must never fail the run it surrounds
        return None
    found = {name: re.search(pattern, screen) for name, pattern in _METERS.items()}
    if not found["week_percent"]:
        return None
    return {name: int(match.group(1)) for name, match in found.items() if match}


class ClaudeCodeProvider:
    """Run a Responses-shaped request through the Claude Code CLI on the owner's subscription.

    One headless ``claude -p`` call per request: a fresh session with no tools,
    no MCP servers and no project context, so the input is the prompt alone.
    It takes the same request body the OpenAI provider takes and returns a body
    of the same shape, so the jobs that call ``respond`` need no other change.

    The CLI needs the owner's login, so this runs only where that login is: a
    worker or management command on the owner's machine, never the deployed
    worker. Editions produced this way reach other environments as promotion
    bundles, like any other edition. There is no Batch service behind it.
    """

    name = "claude-code"

    def __init__(
        self,
        *,
        model: str | None = None,
        binary: str | None = None,
        timeout_seconds: float | None = None,
        runner: Callable[..., Any] = subprocess.run,
        pause: Callable[[float], None] = time.sleep,
    ) -> None:
        self.model = model or settings.CLAUDE_CODE_MODEL
        self.binary = binary or settings.CLAUDE_CODE_BINARY
        self.timeout_seconds = timeout_seconds or settings.CLAUDE_CODE_TIMEOUT_SECONDS
        self.runner = runner
        self.pause = pause
        # An empty directory: the CLI loads CLAUDE.md, memory and project
        # settings from where it runs, and none of that belongs in a request.
        self.workdir = Path(tempfile.gettempdir()) / "almonium-claude-code-empty"
        self.workdir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _cli_schema(schema: dict[str, Any]) -> str:
        """The CLI validates draft-07 shapes: no ``$schema`` and ``definitions`` for ``$defs``."""

        converted = dict(schema)
        converted.pop("$schema", None)
        if "$defs" in converted:
            converted["definitions"] = converted.pop("$defs")
        return json.dumps(converted, ensure_ascii=False).replace("#/$defs/", "#/definitions/")

    def respond(self, body: dict[str, Any]) -> dict[str, Any]:
        """One request, tried once more if the CLI fails in passing."""

        return tried_twice(lambda: self._ask(body), pause=self.pause)

    def _ask(self, body: dict[str, Any]) -> dict[str, Any]:
        text_format = (body.get("text") or {}).get("format") or {}
        schema = text_format.get("schema")
        if not schema:
            raise ValueError("Claude Code requests need a JSON schema for the output")
        effort = (body.get("reasoning") or {}).get("effort", "medium")
        # The prompt goes in on standard input: a chapter's worth of findings with their
        # blocks is longer than the operating system lets a single argument be.
        command = [
            self.binary,
            "-p",
            "--model",
            self.model,
            "--effort",
            effort,
            "--tools",
            "",
            "--system-prompt",
            body["instructions"],
            "--json-schema",
            self._cli_schema(schema),
            "--output-format",
            "json",
            "--no-session-persistence",
            "--strict-mcp-config",
            "--mcp-config",
            '{"mcpServers": {}}',
        ]
        completed = self.runner(
            command,
            input=body["input"],
            capture_output=True,
            text=True,
            timeout=self.timeout_seconds,
            cwd=self.workdir,
            env=UNCACHED,
        )
        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout or "").strip()[-500:]
            raise RuntimeError(f"Claude Code exited with {completed.returncode}: {detail}")
        try:
            result = json.loads(completed.stdout)
        except json.JSONDecodeError as error:
            raise RuntimeError("Claude Code returned output that is not JSON") from error
        usage = result.get("usage") or {}
        cache_read = usage.get("cache_read_input_tokens") or 0
        cache_write = usage.get("cache_creation_input_tokens") or 0
        thinking = (usage.get("output_tokens_details") or {}).get("thinking_tokens") or 0
        spent = {
            # Responses usage counts cached tokens inside input_tokens; the CLI
            # reports them apart, so they are added back here.
            "usage": {
                "input_tokens": (usage.get("input_tokens") or 0) + cache_read + cache_write,
                "output_tokens": usage.get("output_tokens") or 0,
                "input_tokens_details": {"cached_tokens": cache_read},
                "output_tokens_details": {"reasoning_tokens": thinking},
            },
            "claude_code": {
                "duration_ms": result.get("duration_ms"),
                "api_equivalent_cost_usd": result.get("total_cost_usd"),
            },
        }
        try:
            if result.get("is_error"):
                raise RuntimeError(
                    f"Claude Code reported an error: {str(result.get('result'))[:500]}"
                )
            structured = result.get("structured_output")
            if structured is None:
                raise RuntimeError("Claude Code returned no structured output")
            fits_schema(structured, schema)
        except RuntimeError as failure:
            # the call was paid for whether or not its answer can be used
            raise CallFailed(
                str(failure), spent if result.get("total_cost_usd") else None
            ) from failure
        return {
            "id": result.get("session_id") or f"claude-code-{uuid.uuid4()}",
            "model": self.model,
            # the CLI answered in full or raised above; callers shaped for the API ask
            "status": "completed",
            "output": [
                {
                    "type": "message",
                    "content": [
                        {
                            "type": "output_text",
                            "text": json.dumps(structured, ensure_ascii=False),
                        }
                    ],
                }
            ],
            **spent,
        }

    def submit(self, requests, *, metadata):  # noqa: ARG002
        raise NotImplementedError("Claude Code has no Batch service; run requests directly")

    def retrieve(self, batch_id):  # noqa: ARG002
        raise NotImplementedError("Claude Code has no Batch service; run requests directly")

    def cancel(self, batch_id):  # noqa: ARG002
        raise NotImplementedError("Claude Code has no Batch service; run requests directly")

    def output_lines(self, output_file_id):  # noqa: ARG002
        raise NotImplementedError("Claude Code has no Batch service; run requests directly")
