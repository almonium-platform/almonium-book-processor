from __future__ import annotations

import contextlib
import logging
import math
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

import numpy as np
from django.conf import settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class AlignmentCandidate:
    source_indices: tuple[int, ...]
    target_indices: tuple[int, ...]
    confidence: float

    @property
    def source_index(self) -> int:
        return self.source_indices[0]

    @property
    def target_index(self) -> int:
        return self.target_indices[0]


@lru_cache(maxsize=8)
def _spacy_pipeline(language: str) -> Any:
    try:
        import spacy
    except ImportError as error:
        raise RuntimeError("Install the worker dependency group to use NLP processing") from error

    model_name = settings.NLP_SPACY_MODELS.get(language)
    if model_name:
        try:
            return spacy.load(model_name, exclude=["ner", "lemmatizer"])
        except OSError:
            logger.warning(
                "spaCy model %r for %r is not installed; splitting sentences with a blank "
                "pipeline, which is rule-based and weaker than the model.",
                model_name,
                language,
            )

    try:
        pipeline = spacy.blank(language)
    except ValueError:
        pipeline = spacy.blank("xx")
    pipeline.add_pipe("sentencizer")
    return pipeline


def split_sentences(text: str, language: str) -> list[str]:
    """Split text locally; a blank-language sentencizer is the model-free fallback."""

    document = _spacy_pipeline(language)(text)
    return [sentence.text.strip() for sentence in document.sents if sentence.text.strip()]


@dataclass(frozen=True, slots=True)
class EmbeddingRuntime:
    """Where and how embeddings are computed; recorded beside what they produce."""

    device: str
    precision: str
    batch_size: int

    def as_record(self) -> dict[str, str]:
        return {"device": self.device, "precision": self.precision}


def _cpu_has_native_bf16(torch: Any) -> bool:
    """bf16 is only faster where the CPU multiplies in it; elsewhere it is emulated and slower."""

    import platform

    machine = platform.machine().lower()
    if machine in {"x86_64", "amd64"}:
        cpu = getattr(torch, "cpu", None)
        checks = ("_is_avx512_bf16_supported", "_is_amx_tile_supported")
        return any(bool(getattr(cpu, name, lambda: False)()) for name in checks)
    if machine in {"aarch64", "arm64"}:
        try:
            with open("/proc/cpuinfo", encoding="utf-8") as cpuinfo:
                return any(
                    line.lower().startswith("features") and " bf16" in f" {line.lower()}"
                    for line in cpuinfo
                )
        except OSError:
            return False
    return False


def _resolve_runtime(torch: Any, device: str, precision: str, batch_size: int) -> EmbeddingRuntime:
    if device == "auto":
        mps = getattr(torch.backends, "mps", None)
        if torch.cuda.is_available():
            device = "cuda"
        elif mps is not None and mps.is_available():
            device = "mps"
        else:
            device = "cpu"
    if precision == "auto":
        if device == "cuda":
            precision = "bf16" if torch.cuda.is_bf16_supported() else "fp16"
        elif device == "cpu" and _cpu_has_native_bf16(torch):
            precision = "bf16"
        else:
            precision = "fp32"
    if precision not in {"fp32", "bf16", "fp16"}:
        raise ValueError(f"Unknown embedding precision {precision!r}")
    return EmbeddingRuntime(device, precision, batch_size or (32 if device == "cpu" else 128))


def embedding_runtime() -> EmbeddingRuntime:
    """The device, precision and batch size an embedding made here and now runs with.

    Inside ``remote_embeddings.public_text()`` with NLP_EMBEDDING_BACKEND=modal that is the
    Modal GPU; everywhere else it is this process's own hardware, decided once.
    """

    from almonium_book_processor.processing import remote_embeddings

    if remote_embeddings.active():
        return EmbeddingRuntime(
            # which card ran each call is recorded beside the run's usage
            "modal",
            remote_embeddings.precision(),
            settings.NLP_EMBEDDING_BATCH_SIZE or 128,
        )
    return _local_runtime()


@lru_cache(maxsize=1)
def _local_runtime() -> EmbeddingRuntime:
    """The device, precision and batch size this process embeds with, decided once."""

    try:
        import torch
    except ImportError:  # no worker extra: nothing can embed, and nothing reduces precision
        return EmbeddingRuntime("cpu", "fp32", settings.NLP_EMBEDDING_BATCH_SIZE or 32)
    if settings.NLP_EMBEDDING_THREADS:
        torch.set_num_threads(settings.NLP_EMBEDDING_THREADS)
    runtime = _resolve_runtime(
        torch,
        settings.NLP_EMBEDDING_DEVICE,
        settings.NLP_EMBEDDING_PRECISION,
        settings.NLP_EMBEDDING_BATCH_SIZE,
    )
    logger.info(
        "Embeddings on %s in %s, batches of %s, %s torch threads",
        runtime.device,
        runtime.precision,
        runtime.batch_size,
        torch.get_num_threads(),
    )
    return runtime


@lru_cache(maxsize=2)
def _embedding_model(model_name: str) -> Any:
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError as error:
        raise RuntimeError("Install the worker dependency group to compute embeddings") from error
    # Under Modal this copy only tokenizes and chunks; it always lives on local hardware.
    return SentenceTransformer(model_name, device=_local_runtime().device)


def _encode(model: Any, texts: list[str], model_name: str) -> np.ndarray:
    """The model's forward pass in the runtime's precision; vectors come back as float32."""

    if not texts:
        return np.zeros((0, 0), dtype=np.float32)
    runtime = embedding_runtime()
    if runtime.device == "modal":
        from almonium_book_processor.processing import remote_embeddings

        return remote_embeddings.encode(model_name, texts, runtime.batch_size)
    context = contextlib.nullcontext()
    if runtime.precision != "fp32":
        import torch

        dtype = torch.bfloat16 if runtime.precision == "bf16" else torch.float16
        context = torch.autocast(device_type=runtime.device, dtype=dtype)
    with context:
        vectors = model.encode(
            texts,
            batch_size=runtime.batch_size,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
    return np.asarray(vectors, dtype=np.float32)


def embed_texts(
    texts: list[str],
    *,
    reject_truncation: bool = False,
    chunk_long: bool = False,
    model_name: str | None = None,
) -> list[list[float]]:
    """Create normalized multilingual embeddings with the configured local model."""

    model_name = model_name or settings.NLP_EMBEDDING_MODEL
    model = _embedding_model(model_name)
    if chunk_long:
        # Split original text, then re-tokenize every leaf, including special tokens.
        # No decoded-token round trip and no silent encoder truncation.
        tokenizer = model.tokenizer
        limit = model.max_seq_length
        special = tokenizer.num_special_tokens_to_add()
        chunks, owners, weights = [], [], []

        def collect(text, owner, ids=None, depth=0):
            if ids is None:
                ids = tokenizer(text, truncation=False, padding=False)["input_ids"]
            if len(ids) <= limit:
                chunks.append(text)
                owners.append(owner)
                weights.append(max(1, len(ids) - special))
                return
            if depth >= 12 or len(text) < 2:
                raise ValueError("Sentence exceeds embedding token limit")
            middle = len(text) // 2
            spaces = [
                i
                for i, c in enumerate(text)
                if c.isspace() and len(text) // 4 <= i <= 3 * len(text) // 4
            ]
            split = min(spaces, key=lambda i: abs(i - middle)) + 1 if spaces else middle
            collect(text[:split], owner, None, depth + 1)
            collect(text[split:], owner, None, depth + 1)

        # One batched call tokenizes every text; only the few too long for the encoder
        # are split and their pieces tokenized one by one.
        first = tokenizer(list(texts), truncation=False, padding=False)["input_ids"]
        for owner, (text, ids) in enumerate(zip(texts, first, strict=True)):
            collect(text, owner, ids)
        if not chunks:
            return []
        encoded = np.asarray(_encode(model, chunks, model_name), dtype=float)
        # Each text's pieces are consecutive: their token-weighted sum, normalized, is the
        # text's vector. One reduction, not a scan of every piece for every text.
        owner_ids = np.asarray(owners)
        starts = np.flatnonzero(np.r_[True, owner_ids[1:] != owner_ids[:-1]])
        sums = np.add.reduceat(encoded * np.asarray(weights, dtype=float)[:, None], starts, axis=0)
        norms = np.linalg.norm(sums, axis=1, keepdims=True)
        return (sums / np.where(norms, norms, 1.0)).tolist()
    if reject_truncation:
        tokens = model.tokenizer(texts, truncation=False, padding=False)["input_ids"]
        if any(len(ids) > model.max_seq_length for ids in tokens):
            raise ValueError("Sentence exceeds embedding token limit")
    return [vector.tolist() for vector in _encode(model, texts, model_name)]


def _cosine(left, right) -> float:
    left, right = np.asarray(left, dtype=float), np.asarray(right, dtype=float)
    if left.shape != right.shape:
        raise ValueError("Vectors must have the same dimensions")
    norms = float(np.linalg.norm(left) * np.linalg.norm(right))
    return float(left @ right) / norms if norms else 0.0


def _mean_vector(vectors) -> list[float]:
    return np.mean(np.asarray(vectors, dtype=float), axis=0).tolist()


def aggregate_embeddings(
    vectors: list[list[float]],
    groups: list[list[int]],
) -> list[list[float]]:
    """Aggregate normalized block embeddings into normalized group embeddings.

    Chapter alignment uses this to compare chapter semantics before block-level
    alignment.  Normalising the means keeps cosine scores comparable even when
    chapters contain different numbers of blocks.
    """

    aggregates: list[list[float]] = []
    for indices in groups:
        if not indices:
            raise ValueError("Embedding groups cannot be empty")
        mean = _mean_vector([vectors[index] for index in indices])
        norm = math.sqrt(sum(value * value for value in mean))
        aggregates.append([value / norm for value in mean] if norm else mean)
    return aggregates


def _alignment_confidence(
    source: list[list[float]],
    target: list[list[float]],
    source_lengths: list[int] | None,
    target_lengths: list[int] | None,
    source_indices: tuple[int, ...],
    target_indices: tuple[int, ...],
) -> float:
    semantic = max(
        0.0,
        _cosine(
            _mean_vector([source[index] for index in source_indices]),
            _mean_vector([target[index] for index in target_indices]),
        ),
    )
    if source_lengths is None or target_lengths is None:
        return semantic
    source_length = sum(source_lengths[index] for index in source_indices)
    target_length = sum(target_lengths[index] for index in target_indices)
    length_prior = (
        min(source_length, target_length) / max(source_length, target_length)
        if source_length and target_length
        else 0.0
    )
    return 0.9 * semantic + 0.1 * length_prior


def _confidence_table(
    source: Any,
    target: Any,
    source_lengths: list[int] | None,
    target_lengths: list[int] | None,
) -> Any:
    """_alignment_confidence for every window of one to three items, computed up front.

    The dynamic programme asks for the confidence of every 1-3 source window against
    every 1-3 target window. Each window's mean, normalized, is computed once, and the
    cosines of all windows of two sizes are one matrix product, so a paragraph of a few
    hundred chunks costs nine products instead of a Python mean and cosine per cell.
    """

    def unit_windows(vectors: Any) -> dict[int, Any]:
        matrix = np.asarray(vectors, dtype=float)
        sums = np.vstack([np.zeros((1, matrix.shape[1])), np.cumsum(matrix, axis=0)])
        windows = {}
        for size in (1, 2, 3):
            if len(matrix) >= size:
                means = (sums[size:] - sums[:-size]) / size
                norms = np.linalg.norm(means, axis=1, keepdims=True)
                windows[size] = means / np.where(norms, norms, 1.0)
        return windows

    source_windows, target_windows = unit_windows(source), unit_windows(target)
    cosines = {
        (source_size, target_size): np.maximum(
            source_windows[source_size] @ target_windows[target_size].T, 0.0
        )
        for source_size in source_windows
        for target_size in target_windows
    }

    def confidence(source_indices: tuple[int, ...], target_indices: tuple[int, ...]) -> float:
        semantic = float(
            cosines[(len(source_indices), len(target_indices))][
                source_indices[0], target_indices[0]
            ]
        )
        if source_lengths is None or target_lengths is None:
            return semantic
        source_length = sum(source_lengths[index] for index in source_indices)
        target_length = sum(target_lengths[index] for index in target_indices)
        length_prior = (
            min(source_length, target_length) / max(source_length, target_length)
            if source_length and target_length
            else 0.0
        )
        return 0.9 * semantic + 0.1 * length_prior

    return confidence


def align_embeddings(
    source: list[list[float]],
    target: list[list[float]],
    *,
    source_lengths: list[int] | None = None,
    target_lengths: list[int] | None = None,
    minimum_confidence: float = 0.55,
    skip_penalty: float = 0.15,
    sentence_groups: bool = False,
) -> list[AlignmentCandidate]:
    """Return monotonic 1:1, 1:2, and 2:1 candidates for review.

    Embedding similarity is the primary signal. When character lengths are
    supplied, a small Gale-Church-style length prior helps disambiguate nearby
    candidates without assuming translations have identical lengths.
    """

    if len(source) == 0 or len(target) == 0:
        return []
    dimensions = {len(vector) for vector in [*source, *target]}
    if len(dimensions) != 1:
        raise ValueError("All embeddings must use the same dimensions")
    if source_lengths is not None and len(source_lengths) != len(source):
        raise ValueError("source_lengths must match the source vectors")
    if target_lengths is not None and len(target_lengths) != len(target):
        raise ValueError("target_lengths must match the target vectors")

    confidence_of = _confidence_table(source, target, source_lengths, target_lengths)
    best = [[float("-inf")] * (len(target) + 1) for _ in range(len(source) + 1)]
    decision = [["done"] * (len(target) + 1) for _ in range(len(source) + 1)]
    best[len(source)][len(target)] = 0.0
    for source_index in range(len(source) - 1, -1, -1):
        best[source_index][len(target)] = best[source_index + 1][len(target)] - skip_penalty
        decision[source_index][len(target)] = "skip_source"
    for target_index in range(len(target) - 1, -1, -1):
        best[len(source)][target_index] = best[len(source)][target_index + 1] - skip_penalty
        decision[len(source)][target_index] = "skip_target"

    for source_index in range(len(source) - 1, -1, -1):
        for target_index in range(len(target) - 1, -1, -1):
            choices = [
                (best[source_index + 1][target_index] - skip_penalty, "skip_source"),
                (best[source_index][target_index + 1] - skip_penalty, "skip_target"),
            ]
            moves = [
                (1, 1, "match_1_1"),
                (1, 2, "match_1_2"),
                (2, 1, "match_2_1"),
            ]
            if sentence_groups:
                moves.extend([(2, 2, "match_2_2"), (1, 3, "match_1_3"), (3, 1, "match_3_1")])
            for source_count, target_count, action in moves:
                next_source = source_index + source_count
                next_target = target_index + target_count
                if next_source > len(source) or next_target > len(target):
                    continue
                source_indices = tuple(range(source_index, next_source))
                target_indices = tuple(range(target_index, next_target))
                confidence = confidence_of(source_indices, target_indices)
                if confidence >= minimum_confidence:
                    consumed = (source_count + target_count) / 2
                    choices.append(
                        (
                            confidence * consumed
                            + best[next_source][next_target]
                            - (0.08 * (source_count + target_count - 2) if sentence_groups else 0),
                            action,
                        )
                    )
            best[source_index][target_index], decision[source_index][target_index] = max(choices)

    candidates: list[AlignmentCandidate] = []
    source_index = 0
    target_index = 0
    while source_index < len(source) and target_index < len(target):
        action = decision[source_index][target_index]
        if action.startswith("match_"):
            source_count, target_count = {
                "match_1_1": (1, 1),
                "match_1_2": (1, 2),
                "match_2_1": (2, 1),
                "match_2_2": (2, 2),
                "match_1_3": (1, 3),
                "match_3_1": (3, 1),
            }[action]
            source_indices = tuple(range(source_index, source_index + source_count))
            target_indices = tuple(range(target_index, target_index + target_count))
            candidates.append(
                AlignmentCandidate(
                    source_indices,
                    target_indices,
                    confidence_of(source_indices, target_indices),
                )
            )
            source_index += source_count
            target_index += target_count
        elif action == "skip_source":
            source_index += 1
        else:
            target_index += 1
    return candidates
