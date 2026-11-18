"""Embeddings on Modal: only public text leaves, every call is metered, errors say what to fix.

A fake ``modal`` module stands in for the SDK; CI never reaches Modal.
"""

from __future__ import annotations

import sys
import types
from datetime import timedelta
from decimal import Decimal

import numpy as np
import pytest
from django.utils import timezone

from almonium_book_processor.catalog import estimates
from almonium_book_processor.catalog.models import Edition, PipelineRun, Work
from almonium_book_processor.catalog.spend_guard import guard_report
from almonium_book_processor.processing import remote_embeddings


class NotFoundError(Exception):
    pass


@pytest.fixture
def fake_modal(monkeypatch, settings):
    settings.NLP_EMBEDDING_BACKEND = "modal"
    settings.MODAL_EMBEDDING_GPUS = ["L4", "A10"]
    settings.NLP_EMBEDDING_PRECISION = "auto"
    calls = []

    class Method:
        def __init__(self, model_name):
            self.model_name = model_name

        def remote(self, texts, precision, batch_size):
            calls.append((self.model_name, list(texts), precision, batch_size))
            if texts == ["missing app"]:
                raise NotFoundError("App not found")
            vectors = np.arange(len(texts) * 3, dtype=np.float32).reshape(len(texts), 3)
            gpu = "L4" if len(calls) == 1 else "A10"
            return {
                "vectors": vectors.tobytes(),
                "shape": [len(texts), 3],
                "seconds": 1.5,
                "gpu": gpu,
            }

    class Embedder:
        def __init__(self, model_name):
            self.encode = Method(model_name)

    class Cls:
        @staticmethod
        def from_name(app, name):
            assert (app, name) == ("almonium-books-embeddings", "Embedder")
            return Embedder

    module = types.SimpleNamespace(Cls=Cls)
    monkeypatch.setitem(sys.modules, "modal", module)
    remote_embeddings._embedder.cache_clear()
    monkeypatch.setattr(remote_embeddings, "_usage", remote_embeddings.Usage())
    yield calls
    remote_embeddings._embedder.cache_clear()


def test_only_text_marked_public_is_sent(fake_modal):
    assert not remote_embeddings.active()
    with pytest.raises(remote_embeddings.RemoteEmbeddingError, match="public"):
        remote_embeddings.encode("m", ["private upload"], 128)
    assert fake_modal == []
    with remote_embeddings.public_text():
        assert remote_embeddings.active()
    assert not remote_embeddings.active()


def test_local_backend_never_goes_remote(fake_modal, settings):
    settings.NLP_EMBEDDING_BACKEND = "local"
    with remote_embeddings.public_text():
        assert not remote_embeddings.active()


def test_vectors_come_back_in_order_and_every_call_is_metered(fake_modal):
    before = remote_embeddings.usage()
    with remote_embeddings.public_text():
        vectors = remote_embeddings.encode("labse", ["a", "b"], 128)
        remote_embeddings.encode("labse", ["c"], 128)
    assert vectors.dtype == np.float32
    assert vectors.tolist() == [[0, 1, 2], [3, 4, 5]]
    assert fake_modal[0] == ("labse", ["a", "b"], "bf16", 128)
    spent = remote_embeddings.usage().since(before)
    assert (spent.calls, spent.texts, spent.seconds) == (2, 3, 3.0)
    # each call priced at the card that ran it
    assert spent.seconds_by_gpu == {"L4": 1.5, "A10": 1.5}
    assert spent.usd == remote_embeddings.cost_usd(1.5, gpu="L4") + remote_embeddings.cost_usd(
        1.5, gpu="A10"
    )


def test_a_t4_runs_in_fp16_and_an_explicit_precision_wins(fake_modal, settings):
    settings.MODAL_EMBEDDING_GPUS = ["L4", "T4"]
    assert remote_embeddings.precision() == "fp16"
    settings.NLP_EMBEDDING_PRECISION = "fp32"
    assert remote_embeddings.precision() == "fp32"


def test_an_undeployed_app_says_how_to_deploy_it(fake_modal):
    with (
        remote_embeddings.public_text(),
        pytest.raises(remote_embeddings.RemoteEmbeddingError, match="modal deploy"),
    ):
        remote_embeddings.encode("labse", ["missing app"], 128)
    assert remote_embeddings.usage().calls == 0


def test_cost_counts_gpu_seconds_and_each_container_start_and_idle_tail(settings):
    settings.MODAL_EMBEDDING_GPUS = ["L4", "A10"]
    assert remote_embeddings.cost_usd(15, containers=1, gpu="L4") == (
        Decimal("55") * Decimal("0.000222") * Decimal("1.1")
    )
    # no card named: the dearest the app may be scheduled on
    assert remote_embeddings.cost_usd(15, containers=1) == (
        Decimal("55") * Decimal("0.000306") * Decimal("1.1")
    )
    # Modal schedules an "A10" that reports itself as an A10G; both are priced alike
    assert remote_embeddings.price("A10G") == remote_embeddings.price("A10")
    settings.MODAL_EMBEDDING_GPUS = ["B9000"]
    with pytest.raises(remote_embeddings.RemoteEmbeddingError, match="No price"):
        remote_embeddings.cost_usd(1)


@pytest.mark.django_db
def test_offline_alignment_is_free_on_the_worker_and_priced_on_modal(settings):
    settings.NLP_EMBEDDING_BACKEND = "local"
    assert estimates.offline_alignment(1_000_000, "sentence-transformers/LaBSE") is None
    settings.NLP_EMBEDDING_BACKEND = "modal"
    assert estimates.offline_alignment(0, "sentence-transformers/LaBSE") is None
    settings.MODAL_EMBEDDING_GPUS = ["L4", "A10"]
    labse = estimates.offline_alignment(1_000_000, "sentence-transformers/LaBSE")
    mini = estimates.offline_alignment(1_000_000, "other-model")
    assert Decimal("0.01") < mini.usd < labse.usd < estimates.CONFIRM_ABOVE
    assert "L4, A10" in labse.note
    assert labse.label.startswith("~$")


def _modal_run(edition, key, usd, *, status=PipelineRun.Status.SUCCEEDED):
    return PipelineRun.objects.create(
        edition=edition,
        stage=PipelineRun.Stage.ALIGN,
        processor_version="offline-sentence",
        input_hash=key,
        idempotency_key=key,
        status=status,
        summary={
            "embedding": {"device": "modal", "modal_calls": 3, "gpu_seconds": 12.5, "usd": usd}
        },
    )


@pytest.mark.django_db
def test_past_the_monthly_budget_a_run_embeds_free_on_the_cpu(settings):
    from almonium_book_processor.catalog import budgets

    settings.NLP_EMBEDDING_BACKEND = "modal"
    settings.MODAL_EMBEDDING_GPUS = ["L4", "A10"]
    settings.MODAL_MONTHLY_BUDGET_USD = 1.0
    work = Work.objects.create(slug="b", title="B", author="A")
    edition = Edition.objects.create(work=work, slug="b-en", language="en", status="ready")
    last_month = _modal_run(edition, "last-month", "5.0000")
    PipelineRun.objects.filter(pk=last_month.pk).update(
        updated_at=budgets.month_start() - timedelta(seconds=1)
    )
    _modal_run(edition, "this-month", "0.9900")
    assert budgets.spent("modal") == Decimal("0.99")
    assert budgets.allows("modal", Decimal("0.01"))
    assert not budgets.allows("modal", Decimal("0.02"))
    assert estimates.offline_alignment(1_000_000, "sentence-transformers/LaBSE") is None
    settings.MODAL_MONTHLY_BUDGET_USD = 25.0
    assert "$0.99 of $25.00 used" in estimates.offline_alignment(1_000, "m").note


@pytest.mark.django_db
def test_spend_guard_adds_up_modal_gpu_spend_and_what_failed_runs_paid():
    work = Work.objects.create(slug="w", title="A book", author="Author")
    edition = Edition.objects.create(work=work, slug="w-en", language="en", status="ready")

    _modal_run(edition, "done", "0.0300")
    _modal_run(edition, "broke", "0.0100", status=PipelineRun.Status.FAILED)
    old = _modal_run(edition, "old", "9.0000")
    PipelineRun.objects.filter(pk=old.pk).update(updated_at=timezone.now() - timedelta(days=3))
    PipelineRun.objects.create(
        edition=edition,
        stage=PipelineRun.Stage.ALIGN,
        processor_version="offline-sentence",
        input_hash="cpu",
        idempotency_key="cpu",
        summary={"embedding": {"device": "cpu", "precision": "fp32"}},
    )

    modal = guard_report()["modal_embeddings"]
    assert modal == {"runs": 2, "gpu_seconds": 25.0, "usd": "0.0400", "failed_usd": "0.0100"}


@pytest.mark.django_db
def test_modals_own_bill_is_the_spend_every_environment_shares(monkeypatch, settings):
    from datetime import UTC, date, datetime

    from django.core.cache import cache

    from almonium_book_processor.catalog import budgets, spending_report

    cache.clear()
    asked = []

    def report(*, start, resolution):
        asked.append((start, resolution))
        return [
            types.SimpleNamespace(interval_start=datetime(2026, 11, 17, tzinfo=UTC), cost="0.40"),
            types.SimpleNamespace(interval_start=datetime(2026, 11, 18, tzinfo=UTC), cost="0.25"),
            types.SimpleNamespace(interval_start=datetime(2026, 11, 18, tzinfo=UTC), cost="0.05"),
        ]

    workspace = types.SimpleNamespace(billing=types.SimpleNamespace(report=report))
    module = types.SimpleNamespace(Workspace=types.SimpleNamespace(from_context=lambda: workspace))
    monkeypatch.setitem(sys.modules, "modal", module)
    since = datetime(2026, 11, 1, tzinfo=UTC)

    # no token: Modal is not asked, and the runs' records stand in
    monkeypatch.delenv("MODAL_TOKEN_ID", raising=False)
    assert remote_embeddings.billed_by_day(since) is None

    monkeypatch.setenv("MODAL_TOKEN_ID", "ak-test")
    billed = remote_embeddings.billed_by_day(since)
    assert billed == {date(2026, 11, 17): Decimal("0.40"), date(2026, 11, 18): Decimal("0.30")}
    remote_embeddings.billed_by_day(since)
    assert len(asked) == 1  # cached
    assert budgets.spent("modal", since) == Decimal("0.70")
    now = datetime(2026, 11, 18, 12, tzinfo=UTC)
    days = spending_report.buckets("day", now)
    assert days[-1].values["modal"] == Decimal("0.30")

    # an unreadable bill never stops the work: the records answer instead
    cache.clear()
    monkeypatch.setattr(workspace.billing, "report", lambda **_: 1 / 0)
    assert remote_embeddings.billed_by_day(since) is None
    assert budgets.spent("modal", since) == Decimal("0")
    cache.clear()
