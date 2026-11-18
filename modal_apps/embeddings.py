"""The GPU half of offline embeddings, deployed to Modal and called by the book worker.

The worker keeps everything that decides what is embedded (sentence splitting, chunking a
text that exceeds the model's window, the caches that keep a text from being embedded
twice); this app only runs the forward pass. It holds no book text after a call returns.

Deploy (once per Modal environment, and again whenever this file changes):

    modal deploy modal_apps/embeddings.py

The worker finds it by name (MODAL_EMBEDDING_APP) with the token in MODAL_TOKEN_ID and
MODAL_TOKEN_SECRET. docs/MODAL.md has the rest.
"""

# No ``from __future__ import annotations``: Modal reads the real type of a class parameter.
import os
import time

import modal

APP_NAME = os.environ.get("MODAL_EMBEDDING_APP", "almonium-books-embeddings")
# GPUs in order of preference; Modal schedules the first one with capacity. L4 alone waited
# 13 minutes in Modal's queue on 18 November 2026. All of these multiply in bf16 natively.
GPUS = [g.strip() for g in os.environ.get("MODAL_EMBEDDING_GPUS", "L4,A10,L40S").split(",")]
# Every model offline_sentence_alignment.available_models() can name. Weights are baked
# into the image, so a cold container never downloads from Hugging Face.
MODELS = (
    "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
    "sentence-transformers/LaBSE",
)
# Pinned to the versions the CPU worker runs, so a vector does not depend on where it was
# computed beyond the precision recorded beside it.
PACKAGES = (
    "torch==2.14.1",
    "sentence-transformers==5.7.0",
    "transformers==5.20.2",
    "numpy==2.5.4",
)


def _download_models() -> None:
    from sentence_transformers import SentenceTransformer

    for name in MODELS:
        SentenceTransformer(name)


image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install(*PACKAGES)
    .env({"HF_HOME": "/models"})
    .run_function(_download_models)
    .env({"HF_HUB_OFFLINE": "1"})
)
app = modal.App(APP_NAME, image=image)


@app.cls(
    gpu=GPUS,
    # Idle GPU time is billed, and a cold start on the GPU list takes about 3 s: a container
    # that waits 15 s after its last call stays warm through a run's bursts but is not paid
    # for through the minutes of matching between them.
    scaledown_window=15,
    timeout=600,
    max_containers=2,
)
class Embedder:
    model_name: str = modal.parameter()

    @modal.enter()
    def load(self) -> None:
        from sentence_transformers import SentenceTransformer

        if self.model_name not in MODELS:
            raise ValueError(f"Model {self.model_name!r} is not baked into this image")
        self.model = SentenceTransformer(self.model_name, device="cuda")

    @modal.method()
    def encode(self, texts: list[str], precision: str, batch_size: int) -> dict:
        """Normalized float32 vectors for texts, in order, and the GPU seconds they took."""

        import contextlib

        import numpy as np
        import torch

        started = time.monotonic()
        context = contextlib.nullcontext()
        if precision != "fp32":
            dtype = torch.bfloat16 if precision == "bf16" else torch.float16
            context = torch.autocast(device_type="cuda", dtype=dtype)
        with context:
            vectors = self.model.encode(
                texts,
                batch_size=batch_size,
                normalize_embeddings=True,
                show_progress_bar=False,
            )
        vectors = np.asarray(vectors, dtype=np.float32)
        return {
            "vectors": vectors.tobytes(),
            "shape": list(vectors.shape),
            "seconds": time.monotonic() - started,
            # The card that ran, as Modal names it in GPUS ("NVIDIA L40S" -> "L40S").
            "gpu": torch.cuda.get_device_name(0).removeprefix("NVIDIA ").strip(),
        }
