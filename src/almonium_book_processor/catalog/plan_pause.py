"""Taking a plan account out of the pipeline, and putting it back.

The accounts of each plan are a pool every worker shares: a call takes the first open one in
``CODEX_HOMES`` or ``CLAUDE_CONFIG_DIRS`` order (``ai/cli_calls.on_open_account``), so pausing
an account sends its calls to the next, and with every account of a plan paused a call on that
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

from almonium_book_processor.catalog.models import PlanAccountPause, PlanWorker

logger = logging.getLogger(__name__)

PROVIDERS = ("codex", "claude-code")


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


def is_paused(provider: str, account: str) -> bool:
    return PlanAccountPause.objects.filter(provider=provider, account=account).exists()


def worker_is_paused(worker: PlanWorker, paused: set | None = None) -> bool:  # noqa: ARG001
    """The workers stand still only when every account they could call is paused: with one
    left open on either plan there is work they can do."""

    paused = paused_accounts() if paused is None else paused
    return set(known_accounts()) <= paused


def open_codex_accounts() -> list[Path]:
    """The Codex accounts a call may use now, in the order it tries them."""

    from almonium_book_processor.ai.codex_provider import configured_accounts

    paused = {account for provider, account in paused_accounts() if provider == "codex"}
    return [path for path in configured_accounts() if path.name not in paused]


def open_claude_accounts() -> list[Path]:
    """The Claude accounts a call may use now, in the order it tries them."""

    from almonium_book_processor.ai.claude_code_provider import configured_accounts

    paused = {account for provider, account in paused_accounts() if provider == "claude-code"}
    return [path for path in configured_accounts() if path.name not in paused]


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


def pause_all(*, note: str = "") -> None:
    for provider, account in known_accounts():
        PlanAccountPause.objects.update_or_create(
            provider=provider, account=account, defaults={"note": note[:200]}
        )
    apply_to_workers()


def resume_all() -> None:
    PlanAccountPause.objects.all().delete()
    apply_to_workers()


def set_limit(provider: str, account: str, value: str) -> int | None:
    """Keep the share of the week at which the account pauses itself; empty clears it."""

    from almonium_book_processor.catalog.models import PlanAccount

    if provider not in PROVIDERS:
        raise ValueError(f"Unknown plan provider: {provider}")
    value = value.strip().rstrip("%").strip()
    try:
        limit = int(value) if value else None
    except ValueError:
        raise ValueError("Give the limit as a whole percent, or leave it empty.") from None
    if limit is not None and not 1 <= limit <= 100:
        raise ValueError("Give the limit as a percent from 1 to 100.")
    PlanAccount.objects.update_or_create(
        provider=provider, account=account, defaults={"pause_at_percent": limit}
    )
    return limit


def limit_note(percent: int) -> str:
    return f"Paused at {percent}% limit"


def pause_on_limit(provider: str, account: str, week_percent: int) -> bool:
    """Before a new reading is kept: pause the account when its week crosses its limit.

    Only a crossing counts, from below the limit in the last reading to at or above it now, so
    an account the owner runs on past its limit keeps running until the limit is moved, and
    the week's reset brings it back under to cross again.
    """

    from almonium_book_processor.catalog.models import PlanAccount, PlanMeterReading

    limit = (
        PlanAccount.objects.filter(provider=provider, account=account)
        .values_list("pause_at_percent", flat=True)
        .first()
    )
    if limit is None or week_percent < limit or is_paused(provider, account):
        return False
    last = (
        PlanMeterReading.objects.filter(provider=provider, account=account)
        .values_list("week_percent", flat=True)
        .first()
    )
    if last is not None and last >= limit:
        return False
    pause(provider, account, note=limit_note(limit))
    logger.warning("%s %s reached its %s%% limit and is paused.", provider, account, limit)
    return True


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
