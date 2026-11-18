"""An offline alignment run on Modal: public text goes there inside the budget, and is metered."""

from __future__ import annotations

import sys
import types
from decimal import Decimal

import numpy as np
import pytest

from almonium_book_processor.catalog.models import PipelineRun
from almonium_book_processor.catalog.offline_sentence_alignment import (
    queue_alignment,
    run_alignment,
)
from almonium_book_processor.processing import nlp, remote_embeddings
from tests.catalog.test_sentence_alignment import pair  # noqa: F401

pytestmark = pytest.mark.django_db

VECTORS = {"Hello.": [1, 0], "Hello!": [1, 0], "Again.": [0, 1]}


class Tokenizer:
    def __call__(self, text, **kwargs):
        if isinstance(text, list):  # a batch, as the real tokenizer takes one
            return {"input_ids": [[0, *range(len(item.split())), 0] for item in text]}
        return {"input_ids": [0, *range(len(text.split())), 0]}

    def num_special_tokens_to_add(self):
        return 2


class LocalModel:
    """The worker's own copy: it tokenizes, and embeds only when Modal is not used."""

    tokenizer = Tokenizer()
    max_seq_length = 128

    def __init__(self):
        self.encoded = []

    def encode(self, texts, **kwargs):
        self.encoded += texts
        return [VECTORS[text.strip()] for text in texts]


@pytest.fixture
def stack(monkeypatch, settings):
    settings.NLP_EMBEDDING_BACKEND = "modal"
    settings.MODAL_EMBEDDING_GPUS = ["L4", "A10"]
    settings.NLP_EMBEDDING_PRECISION = "auto"
    local = LocalModel()
    monkeypatch.setattr(nlp, "_embedding_model", lambda _: local)
    monkeypatch.setattr(nlp, "_local_runtime", lambda: nlp.EmbeddingRuntime("cpu", "fp32", 32))
    sent = []

    class Method:
        def remote(self, texts, precision, batch_size):
            sent.append((list(texts), precision))
            vectors = np.asarray([VECTORS[t.strip()] for t in texts], dtype=np.float32)
            return {
                "vectors": vectors.tobytes(),
                "shape": list(vectors.shape),
                "seconds": 2.0,
                "gpu": "A10",
            }

    class Embedder:
        def __init__(self, model_name):
            self.encode = Method()

    module = types.SimpleNamespace(Cls=types.SimpleNamespace(from_name=lambda app, name: Embedder))
    monkeypatch.setitem(sys.modules, "modal", module)
    remote_embeddings._embedder.cache_clear()
    yield local, sent
    remote_embeddings._embedder.cache_clear()


def test_a_public_run_embeds_on_modal_and_records_what_it_bought(pair, stack):  # noqa: F811
    local, sent = stack
    p, s = pair
    run = queue_alignment(p.id, s.id)
    run_alignment(run.id)
    run.refresh_from_db()
    assert run.status == PipelineRun.Status.SUCCEEDED, run.error
    assert local.encoded == []
    assert sorted(sent[0][0]) == ["Again.", "Hello!", "Hello."]
    assert sent[0][1] == "bf16"
    embedding = run.summary["embedding"]
    assert embedding["device"] == "modal"
    assert embedding["gpus"] == {"A10": 2.0}
    assert embedding["precision"] == "bf16"
    assert (embedding["modal_calls"], embedding["modal_texts"]) == (1, 3)
    assert embedding["gpu_seconds"] == 2.0
    expected = remote_embeddings.cost_usd(2.0, gpu="A10") + remote_embeddings.cost_usd(
        0, containers=1
    )
    assert embedding["usd"] == str(expected.quantize(Decimal("0.0001")))
    # Nothing outside the run may reach Modal afterwards.
    assert not remote_embeddings.active()


def test_past_the_budget_the_run_embeds_on_the_worker(pair, stack, settings):  # noqa: F811
    local, sent = stack
    settings.MODAL_MONTHLY_BUDGET_USD = 0.0
    p, s = pair
    run = queue_alignment(p.id, s.id)
    run_alignment(run.id)
    run.refresh_from_db()
    assert run.status == PipelineRun.Status.SUCCEEDED, run.error
    assert sent == []
    assert sorted(local.encoded) == ["Again.", "Hello!", "Hello."]
    assert run.summary["embedding"] == {"device": "cpu", "precision": "fp32"}


def test_a_failed_run_keeps_what_it_paid_modal_on_record(pair, stack, monkeypatch):  # noqa: F811
    _, sent = stack
    p, s = pair
    from almonium_book_processor.catalog import offline_sentence_alignment

    def broken(*args, **kwargs):
        raise RuntimeError("worker lost the database")

    monkeypatch.setattr(offline_sentence_alignment, "correspond", broken)
    run = queue_alignment(p.id, s.id)
    with pytest.raises(RuntimeError):
        run_alignment(run.id)
    run.refresh_from_db()
    assert run.status == PipelineRun.Status.FAILED
    assert len(sent) == 1
    assert run.summary["embedding"]["modal_calls"] == 1
    assert not remote_embeddings.active()
