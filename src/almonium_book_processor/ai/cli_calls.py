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
from pathlib import Path
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
# ... one that holds this text was refused by the owner's monthly cap on the provider ...
BUDGET_REACHED = "Budget reached"
# ... and one that holds this text could not reach the provider at all: the machine's network
# was down, as it was on the evening of 25 October 2026 when every book burned its starts.
NETWORK_DOWN = "Network unreachable"
_NETWORK_DOWN = re.compile(
    r"EAI_AGAIN|ENOTFOUND|ECONNRESET|ECONNREFUSED|ETIMEDOUT|ENETUNREACH|getaddrinfo"
    r"|can.t reach the API server|workspace routing discovery failed|network is unreachable"
    r"|Temporary failure in name resolution",
    re.IGNORECASE,
)
# Codex: "... or try again at Oct 30th, 2026 7:43 PM."; Claude Code: "You've hit your session
# limit · resets 6:10pm (UTC)" (its weekly limit reads the same way).
_TRY_AGAIN = re.compile(r"(?:try again at|resets) ([^.\n\"]+)", re.IGNORECASE)


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


class BudgetReached(AllowanceUsedUp):
    """The owner's monthly cap on a provider is spent (``catalog/budgets.py``).

    An ``AllowanceUsedUp``, so every job records it in full and every production waits on it
    uncounted, as on a plan's wall; its message starts with ``BUDGET_REACHED`` instead.
    """

    def __init__(self, message: str, spent: dict[str, Any] | None = None) -> None:
        CallFailed.__init__(self, f"{BUDGET_REACHED}: {message[:300]}", spent)
        self.until = None


class NetworkDown(CallFailed):
    """The provider could not be reached: the machine's network, not the plan or the book.

    The message starts with ``NETWORK_DOWN`` so a job's error says so in the first words; the
    production holds the book without a start and the meter's timer starts it again once a
    provider answers.
    """

    def __init__(self, message: str, spent: dict[str, Any] | None = None) -> None:
        super().__init__(f"{NETWORK_DOWN}: {message[:300]}", spent)


def recorded_error(error: BaseException, *named: type[BaseException]) -> str:
    """How a failed job records its error.

    A refused plan or an unreachable network is kept in full: it carries no book text, and the
    production waits on it by its first words instead of holding the book. The ``named``
    errors, the job's own messages, are kept in full too; anything else may quote the book and
    is recorded by its type only. Recording the type alone for a refusal held 45 translations
    on 16 November 2026 as "started 2 times and did not finish" while the plans were full.
    """

    if isinstance(error, (AllowanceUsedUp, NetworkDown, *named)):
        return str(error)[:1000]
    return type(error).__name__


def _raise_if_unreachable(error: BaseException, earlier: dict[str, Any] | None = None) -> None:
    """Raise ``NetworkDown`` when the CLI could not reach its provider."""

    if isinstance(error, (NetworkDown, AllowanceUsedUp)) or not _NETWORK_DOWN.search(str(error)):
        return
    spent = together(earlier, spent_by(error) or {}) or None
    raise NetworkDown(str(error), spent) from error


def _raise_if_used_up(error: BaseException, earlier: dict[str, Any] | None = None) -> None:
    """Raise ``AllowanceUsedUp`` when the CLI said the plan's allowance is used up."""

    if isinstance(error, AllowanceUsedUp) or not _ALLOWANCE_USED_UP.search(str(error)):
        return
    spent = together(earlier, spent_by(error) or {}) or None
    raise AllowanceUsedUp(str(error), spent) from error


def spent_by(error: BaseException) -> dict[str, Any] | None:
    """What a failed call had already used, where the CLI said."""

    return getattr(error, "spent", None)


def together(first: dict[str, Any] | None, second: dict[str, Any]) -> dict[str, Any]:
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
        return together(first, call())
    except CallFailed as error:
        _raise_if_used_up(error, first)
        # a network that is still down after the pause is an outage, not a passing blip
        _raise_if_unreachable(error, first)
        error.spent = together(first, error.spent or {})
        raise
    except (RuntimeError, subprocess.TimeoutExpired) as error:
        _raise_if_used_up(error, first)
        _raise_if_unreachable(error, first)
        if first:
            raise CallFailed(str(error) or type(error).__name__, first) from error
        raise


# An account that refused for its allowance is not asked again for this long by this process;
# the refusal is free, but asking it before every call of a chapter is a wasted round trip.
REST_SECONDS = 15 * 60
_resting_until: dict[str, float] = {}


def every_account_paused(plan: str) -> str:
    """A hold's words when no account of a plan may be asked: the meter's timer leaves such a
    book held until one is open again (catalog/management/commands/plan_meter.py)."""

    return f"every {plan} account is paused"


def on_open_account(
    plan: str,
    accounts: list[Path],
    ask: Callable[[Path], dict[str, Any]],
    *,
    pause: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
) -> dict[str, Any]:
    """``ask`` on the first of ``accounts`` that is not resting, tried twice as above.

    The accounts are the open ones in the order the settings name them. One whose allowance is
    used up hands the request to the next and rests; with none left the call raises
    ``AllowanceUsedUp``, which holds the book without a start.
    """

    if not accounts:
        raise AllowanceUsedUp(every_account_paused(plan))
    now = clock()
    refused: AllowanceUsedUp | None = None
    for account in accounts:
        if _resting_until.get(str(account), 0) > now:
            continue
        try:
            answer = tried_twice(lambda on=account: ask(on), pause=pause)
        except AllowanceUsedUp as error:
            _resting_until[str(account)] = now + REST_SECONDS
            if refused is not None:
                error.spent = together(refused.spent, error.spent or {}) or None
            refused = error
            continue
        answer["plan_account"] = account.name
        # a refusal is normally free, but where the CLI said it used tokens they count
        return together(refused.spent, answer) if refused and refused.spent else answer
    if refused is not None:
        raise refused
    raise AllowanceUsedUp(
        f"every open {plan} account refused for its allowance in the last "
        f"{REST_SECONDS // 60} minutes"
    )


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
