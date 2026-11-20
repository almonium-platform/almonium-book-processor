from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
import time
import uuid
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

from django.conf import settings

from almonium_book_processor.ai.cli_calls import (
    AllowanceUsedUp,
    CallFailed,
    every_account_paused,
    fits_schema,
    on_open_account,
)

# The CLI keeps one login a machine user, in the system keyring, so the plan has one account
# here; it is named like the directory that holds the CLI's settings.
ACCOUNT = "antigravity-cli"
EVERY_ACCOUNT_PAUSED = every_account_paused("Gemini")
# One request is one command-line argument, and Linux gives an argument 128 KiB.
ARGUMENT_BYTES = 120_000
_SIGNED_OUT = re.compile(r"authentication (?:required|failed)|not logged in", re.IGNORECASE)


def configured_accounts() -> list[Path]:
    return [Path(ACCOUNT)]


def antigravity_meter(
    *, binary: str | None = None, runner: Callable[..., Any] = subprocess.run
) -> dict[str, Any] | None:
    """The plan's meters as the CLI reports them, or None when they cannot be read.

    ``agy -p /usage`` prints a line a meter, tab-separated: the group of models, which limit,
    the share remaining and when it resets. It asks no model and uses none of the plan. The
    Gemini models share one week and one five-hour session; the Claude and GPT models the plan
    also serves have their own, which nothing here calls.
    """

    try:
        said = runner(
            [binary or settings.ANTIGRAVITY_BINARY, "-p", "/usage"],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=120,
            cwd=_workdir(),
        )
        meter: dict[str, Any] = {}
        for line in (said.stdout or "").splitlines():
            group, _, rest = line.partition("\t")
            parts = rest.split("\t")
            if not group.lower().startswith("gemini") or len(parts) < 3:
                continue
            used = 100 - int(parts[1].strip().rstrip("%"))
            resets = datetime.fromisoformat(parts[2].strip().replace("Z", "+00:00"))
            which = "week" if "week" in parts[0].lower() else "session"
            meter[f"{which}_percent"] = used
            meter[f"{which}_resets_at"] = resets
        return meter if "week_percent" in meter else None
    except Exception:  # a meter that cannot be read must never fail the run it surrounds
        return None


def _workdir() -> Path:
    workdir = Path(tempfile.gettempdir()) / "almonium-antigravity-empty"
    workdir.mkdir(parents=True, exist_ok=True)
    return workdir


class AntigravityProvider:
    """Run a Responses-shaped request through the Antigravity CLI on the owner's Google AI plan.

    One ``agy -p`` call per request, in an empty directory. The CLI takes no system prompt and
    no instruction to use no tools, so the step's instructions go before its input and the
    model is told to answer from the material; a tool that would need leave is refused when no
    one is there to give it. The output schema goes in the request's words and the answer is
    checked here: held to a schema by the provider, Gemini 4 Carbon wrote thinner answers
    (the backend's docs/LEXICON.md, "Hard cases"). The CLI names a model with its effort,
    ``gemini-4-carbon-medium``; a seat names them apart like every other.

    Like the other plan providers it needs a login that exists only on the owner's machine and
    has no Batch service behind it.
    """

    name = "antigravity"

    def __init__(
        self,
        *,
        binary: str | None = None,
        timeout_seconds: float | None = None,
        runner: Callable[..., Any] = subprocess.run,
        pause: Callable[[float], None] = time.sleep,
        accounts: Callable[[], list[Path]] = configured_accounts,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.binary = binary or settings.ANTIGRAVITY_BINARY
        self.timeout_seconds = timeout_seconds or settings.ANTIGRAVITY_TIMEOUT_SECONDS
        self.runner = runner
        self.pause = pause
        self.accounts = accounts
        self.clock = clock
        self.workdir = _workdir()

    def respond(self, body: dict[str, Any]) -> dict[str, Any]:
        from almonium_book_processor.catalog import budgets

        budgets.check("antigravity")  # the owner's monthly cap, before the plan is asked
        return on_open_account(
            "Gemini",
            self.accounts(),
            lambda account: self._ask(body),  # noqa: ARG005 - one login a machine
            pause=self.pause,
            clock=self.clock,
        )

    def _ask(self, body: dict[str, Any]) -> dict[str, Any]:
        schema = ((body.get("text") or {}).get("format") or {}).get("schema")
        if not schema:
            raise ValueError("Antigravity requests need a JSON schema for the output")
        effort = (body.get("reasoning") or {}).get("effort") or "medium"
        prompt = (
            f"{body['instructions']}\n\n"
            "Do not run commands, read files or search the web; answer from the material "
            "below.\n\n"
            f"{body['input']}\n\n"
            "Answer with one JSON object and nothing else, of this shape:\n"
            f"{json.dumps(schema, ensure_ascii=False)}"
        )
        if len(prompt.encode("utf-8")) > ARGUMENT_BYTES:
            # refused before the plan is asked: the CLI takes the request as one argument
            raise ValueError(
                f"The request is {len(prompt.encode('utf-8')):,} bytes; the Antigravity CLI "
                f"takes at most {ARGUMENT_BYTES:,} in one call"
            )
        completed = self.runner(
            [
                self.binary,
                "-p",
                prompt,
                "--model",
                f"{body['model']}-{effort}",
                "--output-format",
                "json",
                "--disable-slash-commands",
            ],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=self.timeout_seconds,
            cwd=self.workdir,
            env={**os.environ},
        )
        lines = [line for line in (completed.stdout or "").splitlines() if line.strip()]
        try:
            result = json.loads(lines[-1]) if lines else {}
        except json.JSONDecodeError:
            result = {}
        used = result.get("usage") or {}
        spent = {
            "usage": {
                "input_tokens": used.get("input_tokens") or 0,
                # the CLI counts thinking apart; the plan and the list price charge it as output
                "output_tokens": (used.get("output_tokens") or 0)
                + (used.get("thinking_tokens") or 0),
                "input_tokens_details": {"cached_tokens": used.get("cache_read_tokens") or 0},
                "output_tokens_details": {"reasoning_tokens": used.get("thinking_tokens") or 0},
            }
        }
        text = result.get("response") or ""
        try:
            if result.get("status") != "SUCCESS" or not text:
                detail = (
                    str(result.get("error") or "")
                    or (completed.stderr or "").strip()[-500:]
                    or str(result.get("status") or "no answer")
                )
                if _SIGNED_OUT.search(detail) or _SIGNED_OUT.search(completed.stderr or ""):
                    # Not an answer and not the work's fault: the CLI lost its login. On 20
                    # November 2026 four calls at once made the system keyring answer late, the
                    # CLI turned to a token file for an hour and every call after was refused.
                    # The work is held like one whose allowance is used up, and asked again.
                    raise AllowanceUsedUp(
                        "The Gemini plan is not signed in: run agy once on the owner's machine"
                    )
                raise RuntimeError(f"Antigravity returned no answer: {detail[:500]}")
            answer_text = text.strip()
            if answer_text.startswith("```"):
                answer_text = answer_text.split("\n", 1)[1].rsplit("```", 1)[0]
            try:
                answer = json.loads(answer_text)
            except json.JSONDecodeError as failure:
                raise RuntimeError("Antigravity returned an answer that is not JSON") from failure
            fits_schema(answer, schema)
        except AllowanceUsedUp:
            raise
        except RuntimeError as failure:
            # the turn was paid for whether or not its answer can be used
            raise CallFailed(str(failure), spent if used else None) from failure
        return {
            "id": f"antigravity-{uuid.uuid4()}",
            "model": body["model"],
            "status": "completed",
            "output": [
                {"type": "message", "content": [{"type": "output_text", "text": answer_text}]}
            ],
            **spent,
        }

    def submit(self, requests, *, metadata):  # noqa: ARG002
        raise NotImplementedError("Antigravity has no Batch service here; run requests directly")

    def retrieve(self, batch_id):  # noqa: ARG002
        raise NotImplementedError("Antigravity has no Batch service here; run requests directly")

    def cancel(self, batch_id):  # noqa: ARG002
        raise NotImplementedError("Antigravity has no Batch service here; run requests directly")

    def output_lines(self, output_file_id):  # noqa: ARG002
        raise NotImplementedError("Antigravity has no Batch service here; run requests directly")
