from __future__ import annotations

import json
import subprocess
import tempfile
import time
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

from django.conf import settings

from almonium_book_processor.ai.cli_calls import tried_twice


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
        )
        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout or "").strip()[-500:]
            raise RuntimeError(f"Claude Code exited with {completed.returncode}: {detail}")
        try:
            result = json.loads(completed.stdout)
        except json.JSONDecodeError as error:
            raise RuntimeError("Claude Code returned output that is not JSON") from error
        if result.get("is_error"):
            raise RuntimeError(f"Claude Code reported an error: {str(result.get('result'))[:500]}")
        structured = result.get("structured_output")
        if structured is None:
            raise RuntimeError("Claude Code returned no structured output")

        usage = result.get("usage") or {}
        cache_read = usage.get("cache_read_input_tokens") or 0
        cache_write = usage.get("cache_creation_input_tokens") or 0
        thinking = (usage.get("output_tokens_details") or {}).get("thinking_tokens") or 0
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

    def submit(self, requests, *, metadata):  # noqa: ARG002
        raise NotImplementedError("Claude Code has no Batch service; run requests directly")

    def retrieve(self, batch_id):  # noqa: ARG002
        raise NotImplementedError("Claude Code has no Batch service; run requests directly")

    def cancel(self, batch_id):  # noqa: ARG002
        raise NotImplementedError("Claude Code has no Batch service; run requests directly")

    def output_lines(self, output_file_id):  # noqa: ARG002
        raise NotImplementedError("Claude Code has no Batch service; run requests directly")
