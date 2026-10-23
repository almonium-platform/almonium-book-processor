from __future__ import annotations

import json
import logging
import os
import re
import sqlite3
import subprocess
import tempfile
import time
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

from django.conf import settings

from almonium_book_processor.ai.cli_calls import CallFailed, fits_schema, tried_twice

logger = logging.getLogger(__name__)


def codex_home(home: str | Path | None = None) -> Path:
    """The directory that holds a Codex account: its login, config and session logs.

    The CLI reads it from ``CODEX_HOME`` and falls back to ``~/.codex``, so a second account
    is a second directory, and a worker started with ``CODEX_HOME`` set works on that account.
    """

    return Path(home or os.environ.get("CODEX_HOME") or Path.home() / ".codex")


def codex_meter(
    *,
    home: str | Path | None = None,
    binary: str | None = None,
    runner: Callable[..., Any] = subprocess.run,
) -> dict[str, Any] | None:
    """An account's weekly meter as the CLI last saw it, or None when it cannot be read.

    The CLI writes the rate limits it was told into the session log of every call that is
    not ephemeral, so this makes one tiny call on the account and reads its newest log.
    ``used_percent`` moves in whole points; ``resets_at`` is when the week starts over.
    """

    account = codex_home(home)
    workdir = Path(tempfile.gettempdir()) / "almonium-codex-empty"
    workdir.mkdir(parents=True, exist_ok=True)
    started, log = time.time(), None
    try:
        runner(
            [
                binary or settings.CODEX_BINARY,
                "exec",
                "-m",
                "gpt-6-sol",
                "--skip-git-repo-check",
                "--json",
                "--sandbox",
                "read-only",
                "-c",
                "mcp_servers={}",
                "-c",
                "model_reasoning_effort=low",
                "Reply with the single word: ok",
            ],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=120,
            cwd=workdir,
            env={**os.environ, "CODEX_HOME": str(account)},
        )
        logs = sorted(
            (account / "sessions").glob("*/*/*/rollout-*.jsonl"),
            key=lambda path: path.stat().st_mtime,
        )
        if logs and logs[-1].stat().st_mtime >= started - 1:
            log = logs[-1]
        text = logs[-1].read_text()
        found = re.findall(r'"primary":\s*(\{[^}]*\})', text)
        plan = re.findall(r'"plan_type":\s*"([^"]*)"', text)
        return {**json.loads(found[-1]), "plan_type": plan[-1] if plan else ""}
    except Exception:  # a meter that cannot be read must never fail the run it surrounds
        return None
    finally:
        if log is not None:
            forget_thread(account, log)


def forget_thread(account: Path, log: Path) -> None:
    """Remove one session the CLI kept: its rollout and its rows in the CLI's databases.

    The meter's probe is a conversation like any other to the CLI, and by 24 October 2026 the
    two accounts listed 2,160 of them. The thread id is the tail of the rollout's name, and
    every table with a ``thread_id`` column is cleared of it, as is the threads table.
    """

    thread_id = log.stem[-36:]
    log.unlink(missing_ok=True)
    for database in account.glob("*.sqlite"):
        try:
            with sqlite3.connect(database, timeout=5) as connection:
                tables = [
                    row[0]
                    for row in connection.execute(
                        "select name from sqlite_master where type = 'table'"
                    )
                ]
                for table in tables:
                    columns = [
                        row[1] for row in connection.execute(f'pragma table_info("{table}")')
                    ]
                    if "thread_id" in columns:
                        connection.execute(
                            f'delete from "{table}" where thread_id = ?', (thread_id,)
                        )
                    elif table == "threads" and "id" in columns:
                        connection.execute("delete from threads where id = ?", (thread_id,))
        except sqlite3.Error as error:
            logger.warning("Could not forget Codex thread %s in %s: %s", thread_id, database, error)


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
        pause: Callable[[float], None] = time.sleep,
    ) -> None:
        self.binary = binary or settings.CODEX_BINARY
        self.timeout_seconds = timeout_seconds or settings.CODEX_TIMEOUT_SECONDS
        self.runner = runner
        self.pause = pause
        self.workdir = Path(tempfile.gettempdir()) / "almonium-codex-empty"
        self.workdir.mkdir(parents=True, exist_ok=True)

    def respond(self, body: dict[str, Any]) -> dict[str, Any]:
        """One request, tried once more if the CLI fails in passing."""

        return tried_twice(lambda: self._ask(body), pause=self.pause)

    def _ask(self, body: dict[str, Any]) -> dict[str, Any]:
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
            elif kind in ("error", "turn.failed") and (
                said := event.get("message") or event.get("error")
            ):
                # the failed turn may say less than the error before it did; keep what was said
                error = str(said)[:500]
        spent = {
            "usage": {
                "input_tokens": usage.get("input_tokens") or 0,
                "output_tokens": usage.get("output_tokens") or 0,
                "input_tokens_details": {"cached_tokens": usage.get("cached_input_tokens") or 0},
                "output_tokens_details": {
                    "reasoning_tokens": usage.get("reasoning_output_tokens") or 0
                },
            }
        }
        try:
            if not text:
                detail = error or (completed.stderr or "").strip()[-500:] or "no answer"
                raise RuntimeError(f"Codex returned no answer: {detail}")
            try:
                answer = json.loads(text)
            except json.JSONDecodeError as failure:
                raise RuntimeError("Codex returned an answer that is not JSON") from failure
            fits_schema(answer, schema)
        except RuntimeError as failure:
            # the turn was paid for whether or not its answer can be used
            raise CallFailed(str(failure), spent if usage else None) from failure
        return {
            "id": f"codex-{uuid.uuid4()}",
            "model": body["model"],
            "status": "completed",
            "output": [{"type": "message", "content": [{"type": "output_text", "text": text}]}],
            **spent,
        }

    def submit(self, requests, *, metadata):  # noqa: ARG002
        raise NotImplementedError("Codex has no Batch service here; run requests directly")

    def retrieve(self, batch_id):  # noqa: ARG002
        raise NotImplementedError("Codex has no Batch service here; run requests directly")

    def cancel(self, batch_id):  # noqa: ARG002
        raise NotImplementedError("Codex has no Batch service here; run requests directly")

    def output_lines(self, output_file_id):  # noqa: ARG002
        raise NotImplementedError("Codex has no Batch service here; run requests directly")
