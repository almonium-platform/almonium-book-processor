from __future__ import annotations

import math
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from django.conf import settings


@dataclass(frozen=True, slots=True)
class AlignmentCandidate:
    source_index: int
    target_index: int
    confidence: float


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


def align_embeddings(
    source: list[list[float]],
    target: list[list[float]],
    *,
    minimum_confidence: float = 0.55,
) -> list[AlignmentCandidate]:
    """Return monotonic one-to-one candidates for later human or AI review."""

    if not source or not target:
        return []
    dimensions = {len(vector) for vector in [*source, *target]}
    if len(dimensions) != 1:
        raise ValueError("All embeddings must use the same dimensions")

    scores = [[_cosine(left, right) for right in target] for left in source]
    best = [[0.0] * (len(target) + 1) for _ in range(len(source) + 1)]
    decision = [["done"] * (len(target) + 1) for _ in range(len(source) + 1)]

    for source_index in range(len(source) - 1, -1, -1):
        for target_index in range(len(target) - 1, -1, -1):
            choices = [
                (best[source_index + 1][target_index], "skip_source"),
                (best[source_index][target_index + 1], "skip_target"),
            ]
            confidence = scores[source_index][target_index]
            if confidence >= minimum_confidence:
                choices.append((confidence + best[source_index + 1][target_index + 1], "match"))
            best[source_index][target_index], decision[source_index][target_index] = max(choices)

    candidates: list[AlignmentCandidate] = []
    source_index = 0
    target_index = 0
    while source_index < len(source) and target_index < len(target):
        action = decision[source_index][target_index]
        if action == "match":
            candidates.append(
                AlignmentCandidate(source_index, target_index, scores[source_index][target_index])
            )
            source_index += 1
            target_index += 1
        elif action == "skip_source":
            source_index += 1
        else:
            target_index += 1
    return candidates
