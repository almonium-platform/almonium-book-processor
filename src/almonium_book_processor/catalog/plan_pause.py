"""Taking a plan account out of the pipeline, and putting it back.

The accounts of each plan are a pool every worker shares: a call takes the first open one in
the order the dashboard sets (``call_order``: by priority, or the least used first when the
plan is balanced; ``ai/cli_calls.on_open_account``), so pausing an account sends its calls to
the next, and with every account of a plan paused a call on that
plan holds its book without a start. Only with every account of both plans paused do the
workers stop taking plan jobs (the queue keeps them; nothing is paid), and that outlives a
worker restart: a worker that starts then stops itself. The dashboard's meter panel has the
buttons; the state is a row per account.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from django.conf import settings
from django.utils import timezone

from almonium_book_processor.catalog.models import (
    PlanAccount,
    PlanAccountPause,
    PlanMeterReading,
    PlanRouting,
    PlanWorker,
)

logger = logging.getLogger(__name__)

PROVIDERS = ("codex", "claude-code", "antigravity")


def worker_accounts() -> dict:
    """The accounts this process works on, from the environment the worker was started with."""

    codex = Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex")
    claude = Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude")
    return {"codex": codex.name, "claude-code": claude.name}


def register_worker(nodename: str) -> PlanWorker:
    """Record this worker and its accounts, so a pause can find it."""

    accounts = worker_accounts()
    name = os.environ.get("PLAN_WORKER_NAME") or nodename.split("@")[0].removeprefix("plans-")
    worker, _ = PlanWorker.objects.update_or_create(
        name=name,
        defaults={
            "nodename": nodename,
            "codex_account": accounts["codex"],
            "claude_account": accounts["claude-code"],
            "seen_at": timezone.now(),
        },
    )
    return worker


def paused_accounts() -> set[tuple[str, str]]:
    return set(PlanAccountPause.objects.values_list("provider", "account"))


def archived_accounts() -> set[tuple[str, str]]:
    return set(PlanAccount.objects.filter(archived=True).values_list("provider", "account"))


def is_paused(provider: str, account: str) -> bool:
    return PlanAccountPause.objects.filter(provider=provider, account=account).exists()


def is_archived(provider: str, account: str) -> bool:
    return PlanAccount.objects.filter(provider=provider, account=account, archived=True).exists()


def worker_is_paused(worker: PlanWorker, paused: set | None = None) -> bool:  # noqa: ARG001
    """The workers stand still only when every account they could call is paused: with one
    left open on either plan there is work they can do."""

    paused = paused_accounts() if paused is None else paused
    return set(known_accounts()) <= paused


def open_codex_accounts() -> list[Path]:
    """The Codex accounts a call may use now, in the order it tries them."""

    from almonium_book_processor.ai.codex_provider import configured_accounts

    blocked = {
        account
        for provider, account in (paused_accounts() | archived_accounts())
        if provider == "codex"
    }
    return call_order("codex", [path for path in configured_accounts() if path.name not in blocked])


def open_claude_accounts() -> list[Path]:
    """The Claude accounts a call may use now, in the order it tries them."""

    from almonium_book_processor.ai.claude_code_provider import configured_accounts

    blocked = {
        account
        for provider, account in (paused_accounts() | archived_accounts())
        if provider == "claude-code"
    }
    return call_order(
        "claude-code", [path for path in configured_accounts() if path.name not in blocked]
    )


def open_antigravity_accounts() -> list[Path]:
    """The Gemini plan's one account, unless the owner has paused or archived it."""

    from almonium_book_processor.ai.antigravity_provider import configured_accounts

    blocked = {
        account
        for provider, account in (paused_accounts() | archived_accounts())
        if provider == "antigravity"
    }
    return [path for path in configured_accounts() if path.name not in blocked]


def routing_mode(provider: str) -> str:
    row = PlanRouting.objects.filter(provider=provider).first()
    return row.mode if row else PlanRouting.Mode.ORDER


def call_order(provider: str, accounts: list[Path]) -> list[Path]:
    """``accounts`` in the order a call tries them, asked afresh for every call.

    In order: by priority, an account without one after those with one, in the settings'
    order. Balanced: the least of its week used first, by the account's last reading; one never
    read goes last, and priority breaks a tie.
    """

    priority = dict(
        PlanAccount.objects.filter(provider=provider, priority__isnull=False).values_list(
            "account", "priority"
        )
    )
    settled = {path.name: index for index, path in enumerate(accounts)}

    def ranked(path: Path) -> tuple:
        return (path.name not in priority, priority.get(path.name, 0), settled[path.name])

    if routing_mode(provider) == PlanRouting.Mode.BALANCED:
        used = week_used(provider, [path.name for path in accounts])
        return sorted(accounts, key=lambda path: (used.get(path.name, 101), *ranked(path)))
    return sorted(accounts, key=ranked)


def week_used(provider: str, accounts: list[str]) -> dict[str, int]:
    """Each account's share of its week used, as last read."""

    used = {}
    for account in accounts:
        reading = (
            PlanMeterReading.objects.filter(provider=provider, account=account)
            .order_by("-created_at")
            .values_list("week_percent", flat=True)
            .first()
        )
        if reading is not None:
            used[account] = reading
    return used


def set_mode(provider: str, mode: str) -> None:
    if provider not in PROVIDERS:
        raise ValueError(f"Unknown plan provider: {provider}")
    if mode not in PlanRouting.Mode.values:
        raise ValueError(f"Unknown routing mode: {mode}")
    PlanRouting.objects.update_or_create(provider=provider, defaults={"mode": mode})


def put_first(provider: str, account: str, accounts: list[str]) -> None:
    """Make ``account`` its plan's first; the others of ``accounts`` keep their order after it."""

    if provider not in PROVIDERS:
        raise ValueError(f"Unknown plan provider: {provider}")
    if account not in accounts:
        raise ValueError(f"{account} is not a {provider} account.")
    ordered = [account, *(other for other in accounts if other != account)]
    for rank, name in enumerate(ordered, start=1):
        PlanAccount.objects.update_or_create(
            provider=provider, account=name, defaults={"priority": rank}
        )


def seed_priorities(provider: str, accounts: list[str]) -> None:
    """Give an account without a priority one after the plan's others, in ``accounts`` order:
    the settings' order is where the dashboard's starts, and the dashboard's is kept."""

    taken = set(
        PlanAccount.objects.filter(provider=provider, priority__isnull=False).values_list(
            "priority", flat=True
        )
    )
    rank = max(taken, default=0)
    for account in accounts:
        row, _ = PlanAccount.objects.get_or_create(provider=provider, account=account)
        if row.priority is None:
            rank += 1
            row.priority = rank
            row.save(update_fields=["priority", "updated_at"])


def pause(provider: str, account: str, *, note: str = "") -> None:
    if provider not in PROVIDERS:
        raise ValueError(f"Unknown plan provider: {provider}")
    PlanAccountPause.objects.update_or_create(
        provider=provider, account=account, defaults={"note": note[:200]}
    )
    apply_to_workers()


def resume(provider: str, account: str) -> None:
    PlanAccountPause.objects.filter(provider=provider, account=account).delete()
    apply_to_workers()


def archive(provider: str, account: str) -> None:
    """Hide an account and stop using it everywhere, while keeping its history for restore."""

    if provider not in PROVIDERS:
        raise ValueError(f"Unknown plan provider: {provider}")
    PlanAccount.objects.update_or_create(
        provider=provider, account=account, defaults={"archived": True}
    )
    apply_to_workers()


def restore(provider: str, account: str) -> None:
    """Bring an archived account back into the dashboard, meters, routing, and writers."""

    if provider not in PROVIDERS:
        raise ValueError(f"Unknown plan provider: {provider}")
    PlanAccount.objects.update_or_create(
        provider=provider, account=account, defaults={"archived": False}
    )
    apply_to_workers()


def pause_all(*, note: str = "") -> None:
    for provider, account in known_accounts():
        PlanAccountPause.objects.update_or_create(
            provider=provider, account=account, defaults={"note": note[:200]}
        )
    apply_to_workers()


def resume_all() -> None:
    PlanAccountPause.objects.all().delete()
    apply_to_workers()


def _parse_percent(value: str) -> int | None:
    value = value.strip().rstrip("%").strip()
    try:
        limit = int(value) if value else None
    except ValueError:
        raise ValueError("Give the limit as a whole percent, or leave it empty.") from None
    if limit is not None and not 1 <= limit <= 100:
        raise ValueError("Give the limit as a percent from 1 to 100.")
    return limit


def set_limit(provider: str, account: str, value: str) -> int | None:
    """Keep the share of the week at which the account pauses itself; empty clears it."""

    from almonium_book_processor.catalog.models import PlanAccount

    if provider not in PROVIDERS:
        raise ValueError(f"Unknown plan provider: {provider}")
    limit = _parse_percent(value)
    PlanAccount.objects.update_or_create(
        provider=provider, account=account, defaults={"pause_at_percent": limit}
    )
    return limit


def set_session_limit(provider: str, account: str, value: str) -> int | None:
    """Keep the share of the session at which the account pauses itself; empty clears it."""

    from almonium_book_processor.catalog.models import PlanAccount

    if provider not in PROVIDERS:
        raise ValueError(f"Unknown plan provider: {provider}")
    limit = _parse_percent(value)
    PlanAccount.objects.update_or_create(
        provider=provider, account=account, defaults={"pause_at_session_percent": limit}
    )
    return limit


def limit_note(percent: int) -> str:
    return f"Paused at {percent}% limit"


def session_limit_note(percent: int) -> str:
    return f"Paused at {percent}% session limit"


def _is_session_limit_note(note: str) -> bool:
    return note.startswith("Paused at ") and note.endswith("% session limit")


def pause_on_limit(
    provider: str,
    account: str,
    week_percent: int,
    session_percent: int | None = None,
) -> bool:
    """Before a new reading is kept: pause the account when its week or session crosses its limit,
    and resume an account paused at its session limit once the session resets under it.

    Only a crossing counts, from below the limit in the last reading to at or above it now, so
    an account the owner runs on past its limit keeps running until the limit is moved, and
    the window's reset brings it back under to cross again.
    """

    from almonium_book_processor.catalog.models import PlanAccount, PlanMeterReading

    limits = (
        PlanAccount.objects.filter(provider=provider, account=account, archived=False)
        .values_list("pause_at_percent", "pause_at_session_percent")
        .first()
    )
    if limits is None:
        return False
    week_limit, session_limit = limits

    existing_pause = PlanAccountPause.objects.filter(provider=provider, account=account).first()
    if existing_pause is not None:
        if (
            _is_session_limit_note(existing_pause.note)
            and session_percent is not None
            and session_limit is not None
            and session_percent < session_limit
        ):
            resume(provider, account)
            logger.info(
                "%s %s session is back under its %s%% limit (%s%%) and is resumed.",
                provider,
                account,
                session_limit,
                session_percent,
            )
        else:
            return False

    last = (
        PlanMeterReading.objects.filter(provider=provider, account=account)
        .values_list("week_percent", "session_percent")
        .first()
    )
    last_week, last_session = last if last is not None else (None, None)

    if (
        week_limit is not None
        and week_percent >= week_limit
        and (last_week is None or last_week < week_limit)
    ):
        pause(provider, account, note=limit_note(week_limit))
        logger.warning("%s %s reached its %s%% limit and is paused.", provider, account, week_limit)
        return True

    if (
        session_limit is not None
        and session_percent is not None
        and session_percent >= session_limit
        and (last_session is None or last_session < session_limit)
    ):
        pause(provider, account, note=session_limit_note(session_limit))
        logger.warning(
            "%s %s reached its %s%% session limit and is paused.",
            provider,
            account,
            session_limit,
        )
        return True

    return False


def known_accounts() -> list[tuple[str, str]]:
    """Every account the settings name or a worker has reported, Codex first."""

    accounts: set[tuple[str, str]] = set()
    for home in settings.CODEX_HOMES or ["~/.codex"]:
        accounts.add(("codex", Path(os.path.expanduser(home)).name))
    for config_dir in settings.CLAUDE_CONFIG_DIRS or ["~/.claude"]:
        accounts.add(("claude-code", Path(os.path.expanduser(config_dir)).name))
    for worker in PlanWorker.objects.all():
        accounts.add(("codex", worker.codex_account))
        accounts.add(("claude-code", worker.claude_account))
    if "antigravity" in {plan.strip() for plan in settings.AI_PLANS.split(",")}:
        from almonium_book_processor.ai.antigravity_provider import ACCOUNT

        accounts.add(("antigravity", ACCOUNT))
    accounts -= archived_accounts()
    return sorted(accounts, key=lambda pair: (pair[0] != "codex", pair[1]))


def apply_to_workers() -> dict[str, bool]:
    """Tell every registered worker whether to take plan jobs; the decision per worker."""

    from almonium_book_processor.config.celery import app

    paused = paused_accounts()
    decided: dict[str, bool] = {}
    for worker in PlanWorker.objects.all():
        stop = worker_is_paused(worker, paused)
        decided[worker.name] = stop
        try:
            if stop:
                app.control.cancel_consumer(settings.PLAN_QUEUE, destination=[worker.nodename])
            else:
                app.control.add_consumer(settings.PLAN_QUEUE, destination=[worker.nodename])
        except Exception:  # the broker may be away; the worker asks again when it starts
            logger.exception("Could not reach worker %s to apply the pause.", worker.nodename)
    return decided


def stop_if_paused(consumer, nodename: str) -> bool:
    """At a worker's start: register it and stand still when one of its accounts is paused."""

    worker = register_worker(nodename)
    if not worker_is_paused(worker):
        return False
    consumer.cancel_task_queue(settings.PLAN_QUEUE)
    logger.warning("Worker %s starts paused: one of its accounts is paused.", worker.name)
    return True
