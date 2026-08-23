from __future__ import annotations

import math
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from django.conf import settings


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
            pass

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


@lru_cache(maxsize=2)
def _embedding_model(model_name: str) -> Any:
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError as error:
        raise RuntimeError("Install the worker dependency group to compute embeddings") from error
    return SentenceTransformer(model_name)


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Create normalized multilingual embeddings with the configured local model."""

    vectors = _embedding_model(settings.NLP_EMBEDDING_MODEL).encode(
        texts,
        normalize_embeddings=True,
        show_progress_bar=False,
    )
    return [vector.tolist() for vector in vectors]


def _cosine(left: list[float], right: list[float]) -> float:
    numerator = sum(a * b for a, b in zip(left, right, strict=True))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if not left_norm or not right_norm:
        return 0.0
    return numerator / (left_norm * right_norm)


def _mean_vector(vectors: list[list[float]]) -> list[float]:
    return [sum(values) / len(vectors) for values in zip(*vectors, strict=True)]


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


def align_embeddings(
    source: list[list[float]],
    target: list[list[float]],
    *,
    source_lengths: list[int] | None = None,
    target_lengths: list[int] | None = None,
    minimum_confidence: float = 0.55,
    skip_penalty: float = 0.15,
) -> list[AlignmentCandidate]:
    """Return monotonic 1:1, 1:2, and 2:1 candidates for review.

    Embedding similarity is the primary signal. When character lengths are
    supplied, a small Gale-Church-style length prior helps disambiguate nearby
    candidates without assuming translations have identical lengths.
    """

    if not source or not target:
        return []
    dimensions = {len(vector) for vector in [*source, *target]}
    if len(dimensions) != 1:
        raise ValueError("All embeddings must use the same dimensions")
    if source_lengths is not None and len(source_lengths) != len(source):
        raise ValueError("source_lengths must match the source vectors")
    if target_lengths is not None and len(target_lengths) != len(target):
        raise ValueError("target_lengths must match the target vectors")

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
            for source_count, target_count, action in (
                (1, 1, "match_1_1"),
                (1, 2, "match_1_2"),
                (2, 1, "match_2_1"),
            ):
                next_source = source_index + source_count
                next_target = target_index + target_count
                if next_source > len(source) or next_target > len(target):
                    continue
                source_indices = tuple(range(source_index, next_source))
                target_indices = tuple(range(target_index, next_target))
                confidence = _alignment_confidence(
                    source,
                    target,
                    source_lengths,
                    target_lengths,
                    source_indices,
                    target_indices,
                )
                if confidence >= minimum_confidence:
                    consumed = (source_count + target_count) / 2
                    choices.append(
                        (
                            confidence * consumed + best[next_source][next_target],
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
            }[action]
            source_indices = tuple(range(source_index, source_index + source_count))
            target_indices = tuple(range(target_index, target_index + target_count))
            candidates.append(
                AlignmentCandidate(
                    source_indices,
                    target_indices,
                    _alignment_confidence(
                        source,
                        target,
                        source_lengths,
                        target_lengths,
                        source_indices,
                        target_indices,
                    ),
                )
            )
            source_index += source_count
            target_index += target_count
        elif action == "skip_source":
            source_index += 1
        else:
            target_index += 1
    return candidates
