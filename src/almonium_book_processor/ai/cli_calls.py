"""A call to a plan's CLI, tried once more when it fails for a passing reason.

A long step makes hundreds of these calls, and before this one timeout or one garbled answer
failed the whole step. The CLI's own failures are worth a second try: it exited with an error,
it timed out, or it answered with something that is not the JSON asked for. A plan whose
allowance is used up is not: the second call would fail the same way.

An answer is also held to the schema the request gave before it is returned. The CLIs ask the
model for that shape, but neither enforces every limit in it (a quote's length, a list's
size), and an answer that breaks one used to fail the step later, past the second try.
"""

from __future__ import annotations

import logging
import re
import subprocess
import time
from collections.abc import Callable
from typing import Any

from jsonschema import Draft202012Validator

logger = logging.getLogger(__name__)

RETRY_PAUSE_SECONDS = 15.0
_ALLOWANCE_USED_UP = re.compile(
    r"usage limit|limit reached|usage_limit|rate limit|quota|hit your (?:weekly |session )?limit"
    r"|out of (?:credits|quota)",
    re.IGNORECASE,
)
# A run's error that holds this text was refused for a used-up allowance, not for its own fault.
ALLOWANCE_USED_UP = "Allowance used up"
_TRY_AGAIN = re.compile(r"try again at ([^.\n]+)", re.IGNORECASE)


class CallFailed(RuntimeError):
    """A CLI call that failed after it had used tokens. ``spent`` says what it used.

    ``spent`` has the shape of a response's cost-bearing parts, its usage and for Claude Code
    the CLI's own price, so that whatever records a response's cost can record a failure's.
    """

    def __init__(self, message: str, spent: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.spent = spent


class AllowanceUsedUp(CallFailed):
    """The plan's weekly allowance is used up: every call on it fails this way until it turns.

    The message starts with ``ALLOWANCE_USED_UP`` so a job's error says so in the first
    words, and ``until`` is when the CLI said to try again, when it said.
    """

    def __init__(self, message: str, spent: dict[str, Any] | None = None) -> None:
        super().__init__(f"{ALLOWANCE_USED_UP}: {message[:300]}", spent)
        found = _TRY_AGAIN.search(message)
        self.until = found.group(1).strip() if found else None


def _raise_if_used_up(error: BaseException, earlier: dict[str, Any] | None = None) -> None:
    """Raise ``AllowanceUsedUp`` when the CLI said the plan's allowance is used up."""

    if isinstance(error, AllowanceUsedUp) or not _ALLOWANCE_USED_UP.search(str(error)):
        return
    spent = _together(earlier, spent_by(error) or {}) or None
    raise AllowanceUsedUp(str(error), spent) from error


def spent_by(error: BaseException) -> dict[str, Any] | None:
    """What a failed call had already used, where the CLI said."""

    return getattr(error, "spent", None)


def _together(first: dict[str, Any] | None, second: dict[str, Any]) -> dict[str, Any]:
    """``second`` carrying the tokens and the price of ``first`` as well: both were paid for."""

    if not first:
        return second
    used, usage = first.get("usage") or {}, second.setdefault("usage", {})
    for key in ("input_tokens", "output_tokens"):
        usage[key] = (usage.get(key) or 0) + (used.get(key) or 0)
    for group, key in (
        ("input_tokens_details", "cached_tokens"),
        ("output_tokens_details", "reasoning_tokens"),
    ):
        details = usage.setdefault(group, {})
        details[key] = (details.get(key) or 0) + ((used.get(group) or {}).get(key) or 0)
    price = (first.get("claude_code") or {}).get("api_equivalent_cost_usd")
    if price is not None:
        priced = second.setdefault("claude_code", {})
        priced["api_equivalent_cost_usd"] = (priced.get("api_equivalent_cost_usd") or 0) + price
    return second


def tried_twice(
    call: Callable[[], dict[str, Any]], *, pause: Callable[[float], None] = time.sleep
) -> dict[str, Any]:
    """``call()``, and once more after a short pause if the CLI failed in passing.

    A call that failed after using tokens is not free. Its tokens are added to the second
    call's when that one answers, and travel with the error when it fails too, so the ledger
    shows what both cost.
    """

    try:
        return call()
    except subprocess.TimeoutExpired as error:
        # The CLI was killed, but the model may well have finished the work and the plan paid
        # for it; asking again pays twice for the slowest call of the book. The window fails,
        # and the next attempt reuses every answer that was kept.
        _raise_if_used_up(error)
        raise CallFailed(
            "The plan CLI gave no answer within its timeout; not asked again in this call.",
            spent_by(error),
        ) from error
    except RuntimeError as error:
        _raise_if_used_up(error)
        first = spent_by(error)
        logger.warning("A plan CLI call failed and is tried once more: %s", str(error)[:300])
    pause(RETRY_PAUSE_SECONDS)
    try:
        return _together(first, call())
    except CallFailed as error:
        _raise_if_used_up(error, first)
        error.spent = _together(first, error.spent or {})
        raise
    except (RuntimeError, subprocess.TimeoutExpired) as error:
        _raise_if_used_up(error, first)
        if first:
            raise CallFailed(str(error) or type(error).__name__, first) from error
        raise


def fits_schema(answer: Any, schema: dict[str, Any]) -> None:
    """Raise unless ``answer`` is the shape that was asked for.

    The error names where the answer breaks the schema and which rule, never the value: an
    answer can quote the book, and an error message is stored and shown.
    """

    error = next(iter(Draft202012Validator(schema).iter_errors(answer)), None)
    if error is not None:
        where = "/".join(str(part) for part in error.absolute_path) or "the answer"
        raise RuntimeError(
            f"The answer does not fit the schema asked for: {where} ({error.validator})"
        )
