"""Taking a plan account out of the pipeline, and putting it back.

A plan worker works on one Codex account and one Claude account. Pausing an account stops
every worker that works on it from taking plan jobs (the queue keeps the jobs; nothing is
paid), and the pause outlives a worker restart: a worker that starts on a paused account
stops itself. The dashboard's meter panel has the buttons; the state is a row per account.
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


def worker_is_paused(worker: PlanWorker, paused: set | None = None) -> bool:
    """A worker stands still when either of its accounts is paused."""

    paused = paused_accounts() if paused is None else paused
    return ("codex", worker.codex_account) in paused or (
        "claude-code",
        worker.claude_account,
    ) in paused


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
