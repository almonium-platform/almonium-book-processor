from __future__ import annotations

import json
import subprocess
import tempfile
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

from django.conf import settings


class CodexProvider:
    """Run a Responses-shaped request through the Codex CLI on the owner's ChatGPT plan.

    One ``codex exec`` call per request: an ephemeral session in an empty directory with a
    read-only sandbox and no MCP servers, the prompt on standard input and the output held to
    the request's JSON schema. It takes the body the OpenAI provider takes and returns a body
    of the same shape, so the jobs that call ``respond`` need no other change.

    Like the Claude Code provider, it needs a login that exists only on the owner's machine,
    so it never runs on a deployed worker and has no Batch service behind it. Every call also
    carries the CLI's own instructions, about fifteen thousand input tokens, mostly cached.
    """

    name = "codex"

    def __init__(
        self,
        *,
        binary: str | None = None,
        timeout_seconds: float | None = None,
        runner: Callable[..., Any] = subprocess.run,
    ) -> None:
        self.binary = binary or settings.CODEX_BINARY
        self.timeout_seconds = timeout_seconds or settings.CODEX_TIMEOUT_SECONDS
        self.runner = runner
        self.workdir = Path(tempfile.gettempdir()) / "almonium-codex-empty"
        self.workdir.mkdir(parents=True, exist_ok=True)

    def respond(self, body: dict[str, Any]) -> dict[str, Any]:
        schema = ((body.get("text") or {}).get("format") or {}).get("schema")
        if not schema:
            raise ValueError("Codex requests need a JSON schema for the output")
        effort = (body.get("reasoning") or {}).get("effort", "medium")
        prompt = (
            f"{body['instructions']}\n\n"
            "Do not run commands or read files; answer from the material below.\n\n"
            f"{body['input']}"
        )
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".schema.json", dir=tempfile.gettempdir(), delete=False
        ) as stream:
            schema_path = Path(stream.name)
            json.dump(schema, stream, ensure_ascii=False)
        try:
            completed = self.runner(
                [
                    self.binary,
                    "exec",
                    "-m",
                    body["model"],
                    "--skip-git-repo-check",
                    "--ephemeral",
                    "--json",
                    "--sandbox",
                    "read-only",
                    "-c",
                    "mcp_servers={}",
                    "-c",
                    f"model_reasoning_effort={effort}",
                    "--output-schema",
                    str(schema_path),
                    # the prompt comes on standard input; an open stdin would make the CLI wait
                    "-",
                ],
                input=prompt,
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
                cwd=self.workdir,
            )
        finally:
            schema_path.unlink(missing_ok=True)

        text, usage, error = "", {}, ""
        for line in (completed.stdout or "").splitlines():
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            kind = event.get("type")
            if (
                kind == "item.completed"
                and (event.get("item") or {}).get("type") == "agent_message"
            ):
                text = event["item"].get("text", "")
            elif kind == "turn.completed":
                usage = event.get("usage") or {}
            elif kind in ("error", "turn.failed"):
                error = str(event.get("message") or event.get("error"))[:500]
        if not text:
            detail = error or (completed.stderr or "").strip()[-500:] or "no answer"
            raise RuntimeError(f"Codex returned no answer: {detail}")
        try:
            json.loads(text)
        except json.JSONDecodeError as failure:
            raise RuntimeError("Codex returned an answer that is not JSON") from failure
        return {
            "id": f"codex-{uuid.uuid4()}",
            "model": body["model"],
            "status": "completed",
            "output": [{"type": "message", "content": [{"type": "output_text", "text": text}]}],
            "usage": {
                "input_tokens": usage.get("input_tokens") or 0,
                "output_tokens": usage.get("output_tokens") or 0,
                "input_tokens_details": {"cached_tokens": usage.get("cached_input_tokens") or 0},
                "output_tokens_details": {
                    "reasoning_tokens": usage.get("reasoning_output_tokens") or 0
                },
            },
        }

    def submit(self, requests, *, metadata):  # noqa: ARG002
        raise NotImplementedError("Codex has no Batch service here; run requests directly")

    def retrieve(self, batch_id):  # noqa: ARG002
        raise NotImplementedError("Codex has no Batch service here; run requests directly")

    def cancel(self, batch_id):  # noqa: ARG002
        raise NotImplementedError("Codex has no Batch service here; run requests directly")

    def output_lines(self, output_file_id):  # noqa: ARG002
        raise NotImplementedError("Codex has no Batch service here; run requests directly")
