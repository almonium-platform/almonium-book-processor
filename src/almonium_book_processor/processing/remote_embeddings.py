"""Embeddings on Modal's GPUs, for a worker whose own CPU is slow at them.

NLP_EMBEDDING_BACKEND=modal sends each forward pass to the app in modal_apps/embeddings.py;
the worker still tokenizes, chunks and caches, so a text is only ever sent when the local
caches miss.

Only public catalogue text leaves the worker. A caller that has checked its work is public
opens ``public_text()`` around the embedding; everywhere else, private uploads included,
the setting is ignored and the worker embeds on its own CPU.

Modal bills GPU seconds against the free monthly credits: every call adds to a process meter
that a run reads before and after its work and records, so the spend is on the run and not
only on Modal's invoice (catalog/budgets.py keeps it inside the credits).
"""

from __future__ import annotations

import logging
import os
from collections import defaultdict
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from functools import lru_cache
from typing import Any

import numpy as np
from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)

# Modal's list prices per GPU second (modal.com/pricing, November 2026), by the name Modal
# schedules a card under and the app reports it by. The container's
# CPU and memory are billed beside the GPU and add about a tenth for these small models.
GPU_USD_PER_SECOND = {
    "T4": Decimal("0.000164"),
    "L4": Decimal("0.000222"),
    "A10": Decimal("0.000306"),
    "A10G": Decimal("0.000306"),  # what Modal's "A10" reports itself as
    "L40S": Decimal("0.000542"),
    "A100-40GB": Decimal("0.000583"),
    "A100-80GB": Decimal("0.000694"),
    "H100": Decimal("0.001097"),
}
OVERHEAD = Decimal("1.1")
# A container that starts for a run loads its model first and idles after the last call
# (scaledown_window in modal_apps/embeddings.py) before Modal stops billing it.
COLD_START_SECONDS = 25
IDLE_SECONDS = 15
# How long Modal's bill is kept: the days under way for ten minutes, a finished 30-day window
# for a week. Nothing was billed before the workspace's first use.
BILLING_CACHE_SECONDS = 600
BILLING_FINISHED_SECONDS = 7 * 24 * 3600
BILLING_EPOCH = datetime(2026, 11, 1, tzinfo=UTC)
# GPUs older than Ampere multiply in fp16 but not bf16.
_NO_BF16 = {"T4"}


_public = ContextVar("public_text", default=False)


@contextmanager
def public_text() -> Iterator[None]:
    """Embeddings inside may go to Modal: the caller has checked the text is public."""

    token = _public.set(True)
    try:
        yield
    finally:
        _public.reset(token)


def active() -> bool:
    """Whether an embedding made here and now runs on Modal."""

    return settings.NLP_EMBEDDING_BACKEND == "modal" and _public.get()


def billed_by_day(since: datetime) -> dict[date, Decimal] | None:
    """What Modal billed the whole workspace per UTC day since ``since``, from its own report.

    The workspace's free credits are spent by every environment that holds the token, so this
    is the figure a cap has to hold, where a run's own record is an estimate of one
    environment's share. None when Modal cannot be asked (no client, no token, an error, its
    rate limit); the caller then falls back to the runs' records.

    Modal's report leaves out the day under way, spans 31 days at most by day and seven by the
    hour, starts no more than a year back, and is rate limited. So whole days come in 30-day
    windows counted from the workspace's first use, a finished window cached for a week (a past
    day's bill does not change); the window under way and today, by the hour, for ten minutes.
    """

    if not os.environ.get("MODAL_TOKEN_ID"):
        return None
    today = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    start = max(BILLING_EPOCH, since, today - timedelta(days=364))
    windows = []
    edge = BILLING_EPOCH + timedelta(days=30) * ((start - BILLING_EPOCH).days // 30)
    while edge < today:
        windows.append((edge, min(edge + timedelta(days=30), today), "d"))
        edge += timedelta(days=30)
    windows.append((today, None, "h"))
    days: dict[date, Decimal] = defaultdict(Decimal)
    for window_start, window_end, resolution in windows:
        found = _billed_window(window_start, window_end, resolution, today)
        if found is None:
            return None
        for day, cost in found.items():
            if day >= start.date():
                days[day] += cost
    return dict(days)


def _billed_window(start, end, resolution, today) -> dict[date, Decimal] | None:
    key = (
        f"modal-billed:{resolution}:{start:%Y%m%d}:{end:%Y%m%d}"
        if end
        else (f"modal-billed:{resolution}:{start:%Y%m%d}")
    )
    found = cache.get(key)
    if found is not None:
        return found
    try:
        import modal

        billing = modal.Workspace.from_context().billing
        if end is None:
            items = billing.report(start=start, resolution=resolution)
        else:
            items = billing.report(start=start, end=end, resolution=resolution)
    except Exception as error:  # the bill is a better figure, never a condition of working
        logger.warning("Could not read Modal's billing report: %s", error)
        return None
    days: dict[date, Decimal] = defaultdict(Decimal)
    for item in items:
        days[item.interval_start.date()] += Decimal(str(item.cost))
    finished = end is not None and end <= today and (end - start).days == 30
    cache.set(key, dict(days), BILLING_FINISHED_SECONDS if finished else BILLING_CACHE_SECONDS)
    return dict(days)


class RemoteEmbeddingError(RuntimeError):
    """Modal could not compute the embeddings; the message says what to fix."""


@dataclass
class Usage:
    calls: int = 0
    texts: int = 0
    seconds: float = 0.0
    # priced call by call at the card that ran it
    usd: Decimal = field(default_factory=Decimal)
    seconds_by_gpu: dict[str, float] = field(default_factory=dict)

    def copy(self) -> Usage:
        return Usage(self.calls, self.texts, self.seconds, self.usd, dict(self.seconds_by_gpu))

    def since(self, earlier: Usage) -> Usage:
        return Usage(
            self.calls - earlier.calls,
            self.texts - earlier.texts,
            self.seconds - earlier.seconds,
            self.usd - earlier.usd,
            {
                gpu: round(seconds - earlier.seconds_by_gpu.get(gpu, 0.0), 2)
                for gpu, seconds in self.seconds_by_gpu.items()
                if seconds != earlier.seconds_by_gpu.get(gpu, 0.0)
            },
        )


_usage = Usage()


def usage() -> Usage:
    """This process's Modal calls so far; subtract an earlier reading to get one run's."""

    return _usage.copy()


def gpus() -> list[str]:
    return list(settings.MODAL_EMBEDDING_GPUS)


def precision() -> str:
    """The precision the remote GPU runs in: bf16 when every listed card has it, else fp16."""

    chosen = settings.NLP_EMBEDDING_PRECISION
    if chosen == "auto":
        return "fp16" if _NO_BF16 & set(gpus()) else "bf16"
    return chosen


def price(gpu: str) -> Decimal:
    try:
        return GPU_USD_PER_SECOND[gpu]
    except KeyError:
        raise RemoteEmbeddingError(f"No price known for Modal GPU {gpu!r}") from None


def cost_usd(seconds: float, *, containers: int = 0, gpu: str | None = None) -> Decimal:
    """What Modal bills for this much GPU time, plus each container's start and idle tail.

    Without a card named, the dearest one the app may be scheduled on: an estimate before
    the call cannot know which card Modal will find free.
    """

    rate = price(gpu) if gpu else max(price(listed) for listed in gpus())
    billed = Decimal(str(seconds)) + containers * (COLD_START_SECONDS + IDLE_SECONDS)
    return billed * rate * OVERHEAD


@lru_cache(maxsize=4)
def _embedder(model_name: str) -> Any:
    try:
        import modal
    except ImportError as error:
        raise RemoteEmbeddingError(
            "Install the worker dependency group to compute embeddings on Modal"
        ) from error
    cls = modal.Cls.from_name(settings.MODAL_EMBEDDING_APP, "Embedder")
    return cls(model_name=model_name)


def _explain(error: Exception) -> str:
    name = type(error).__name__
    if name == "NotFoundError":
        return (
            f"Modal app {settings.MODAL_EMBEDDING_APP!r} is not deployed in this Modal "
            "environment; run `modal deploy modal_apps/embeddings.py` (docs/MODAL.md)."
        )
    if name == "AuthError":
        return "Modal rejected the token; check MODAL_TOKEN_ID and MODAL_TOKEN_SECRET."
    if name == "ResourceExhaustedError":
        return f"Modal refused the call for a quota or spending limit: {error}"
    return f"Modal embeddings failed ({name}): {error}"


def encode(model_name: str, texts: list[str], batch_size: int) -> np.ndarray:
    """Normalized float32 vectors for texts, in order, computed on the remote GPU."""

    if not texts:
        return np.zeros((0, 0), dtype=np.float32)
    if not _public.get():
        raise RemoteEmbeddingError("Only text a caller marked public may be sent to Modal")
    # The vectors come back as float16 when the GPU computes in reduced precision anyway:
    # half the bytes of the transfer that is most of a call's time. fp32 stays exact.
    chosen = precision()
    wire = "float32" if chosen == "fp32" else "float16"
    try:
        answer = _embedder(model_name).encode.remote(texts, chosen, batch_size, wire)
    except RemoteEmbeddingError:
        raise
    except Exception as error:
        raise RemoteEmbeddingError(_explain(error)) from error
    vectors = (
        np.frombuffer(answer["vectors"], dtype=answer.get("dtype", "float32"))
        .reshape(answer["shape"])
        .astype(np.float32)
    )
    if len(vectors) != len(texts):
        raise RemoteEmbeddingError(f"Modal returned {len(vectors)} vectors for {len(texts)} texts")
    seconds = float(answer["seconds"])
    ran_on = str(answer.get("gpu") or "")
    _usage.calls += 1
    _usage.texts += len(texts)
    _usage.seconds += seconds
    _usage.usd += cost_usd(seconds, gpu=ran_on if ran_on in GPU_USD_PER_SECOND else None)
    _usage.seconds_by_gpu[ran_on or "unknown"] = (
        _usage.seconds_by_gpu.get(ran_on or "unknown", 0.0) + seconds
    )
    return vectors
