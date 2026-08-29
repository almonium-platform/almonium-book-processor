from __future__ import annotations

import importlib.metadata
import math
from collections import Counter, defaultdict
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from django.conf import settings

LEXICAL_SCHEMA_VERSION = 1
LEXICAL_PROCESSOR_VERSION = "lexical-v1"
USEFUL_WORD_LIMIT = 50


@dataclass(frozen=True, slots=True)
class LexicalBlock:
    block_id: str
    chapter: int
    text: str


@dataclass(frozen=True, slots=True)
class _Occurrence:
    block_id: str
    chapter: int
    surface: str
    context: str


@lru_cache(maxsize=8)
def _lexical_pipeline(language: str) -> Any:
    try:
        import spacy
    except ImportError as error:
        raise RuntimeError("Install the worker dependency group to analyze vocabulary") from error

    model_name = settings.NLP_SPACY_MODELS.get(language)
    if model_name:
        try:
            return spacy.load(model_name, exclude=["ner"])
        except OSError:
            pass
    try:
        return spacy.blank(language)
    except ValueError:
        return spacy.blank("xx")


def _word_frequency(word: str, language: str) -> float:
    try:
        from wordfreq import zipf_frequency
    except ImportError as error:
        message = "Install the worker dependency group to analyze word frequency"
        raise RuntimeError(message) from error
    return float(zipf_frequency(word, language))


def _context(text: str, start: int, end: int, radius: int = 90) -> str:
    left = max(0, start - radius)
    right = min(len(text), end + radius)
    excerpt = " ".join(text[left:right].split())
    if left:
        excerpt = "…" + excerpt
    if right < len(text):
        excerpt += "…"
    return excerpt


def _frequency_band(zipf: float) -> str:
    if zipf >= 5:
        return "very_common"
    if zipf >= 4:
        return "common"
    if zipf >= 3:
        return "uncommon"
    return "rare"


def _lemma(token: Any, language: str) -> str:
    if token.lemma_:
        return token.lemma_.casefold().strip()
    try:
        import simplemma
    except ImportError as error:
        message = "Install the worker dependency group to lemmatize vocabulary"
        raise RuntimeError(message) from error
    try:
        return simplemma.lemmatize(token.text, lang=language).casefold().strip()
    except ValueError:
        return token.text.casefold().strip()


def _looks_like_proper_name(text: str, token: Any, language: str) -> bool:
    if token.pos_ == "PROPN":
        return True
    if language == "de" or not token.text[:1].isupper():
        return False
    before = text[: token.idx].rstrip().rstrip("\"'“”«»„([{—–")
    return bool(before) and before[-1] not in ".!?…"


def lexical_runtime_signature(language: str) -> dict[str, Any]:
    pipeline = _lexical_pipeline(language)
    model_name = pipeline.meta.get("name") if pipeline.pipe_names else f"blank:{pipeline.lang}"
    return {
        "spacy_version": importlib.metadata.version("spacy"),
        "spacy_model": model_name,
        "spacy_model_version": pipeline.meta.get("version", "0.0.0"),
        "spacy_pipeline": list(pipeline.pipe_names),
        "simplemma_version": importlib.metadata.version("simplemma"),
        "wordfreq_version": importlib.metadata.version("wordfreq"),
    }


def analyze_lexicon(
    blocks: Iterable[LexicalBlock],
    language: str,
    *,
    frequency_lookup: Callable[[str, str], float] = _word_frequency,
    limit: int = USEFUL_WORD_LIMIT,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Build book-level lexical statistics and a useful distinctive-word list.

    Selection is deterministic. It rewards repeated, chapter-dispersed lemmas
    that are uncommon in general language, while excluding stop words, proper
    nouns, hapaxes, and extremely obscure forms that are usually names, OCR
    damage, or poor learning targets.
    """

    blocks = list(blocks)
    pipeline = _lexical_pipeline(language)
    counts: Counter[str] = Counter()
    surfaces: dict[str, Counter[str]] = defaultdict(Counter)
    chapters: dict[str, set[int]] = defaultdict(set)
    occurrences: dict[str, list[_Occurrence]] = defaultdict(list)
    excluded: set[str] = set()
    total_tokens = 0

    for block in blocks:
        document = pipeline(block.text)
        for token in document:
            if not token.is_alpha:
                continue
            total_tokens += 1
            lemma = _lemma(token, language)
            if not lemma:
                continue
            counts[lemma] += 1
            surfaces[lemma][token.text] += 1
            chapters[lemma].add(block.chapter)
            if token.is_stop or _looks_like_proper_name(block.text, token, language):
                excluded.add(lemma)
            if len(occurrences[lemma]) < 3:
                occurrences[lemma].append(
                    _Occurrence(
                        block_id=block.block_id,
                        chapter=block.chapter,
                        surface=token.text,
                        context=_context(block.text, token.idx, token.idx + len(token.text)),
                    )
                )

    frequencies = {lemma: frequency_lookup(lemma, language) for lemma in counts}
    bands = Counter()
    for lemma, count in counts.items():
        bands[_frequency_band(frequencies[lemma])] += count

    candidates = []
    chapter_total = len({item.chapter for item in blocks})
    for lemma, count in counts.items():
        zipf = frequencies[lemma]
        if lemma in excluded or count < 2 or not 2.5 <= zipf <= 5.5:
            continue
        dispersion = len(chapters[lemma]) / max(1, chapter_total)
        rarity = 6.0 - zipf
        score = math.log1p(count) * (0.65 + 0.35 * dispersion) * rarity
        candidates.append(
            {
                "lemma": lemma,
                "display": surfaces[lemma].most_common(1)[0][0],
                "count": count,
                "chapter_count": len(chapters[lemma]),
                "zipf_frequency": round(zipf, 3),
                "frequency_band": _frequency_band(zipf),
                "score": round(score, 6),
                "occurrences": [
                    {
                        "block_id": item.block_id,
                        "chapter": item.chapter,
                        "surface": item.surface,
                        "context": item.context,
                    }
                    for item in occurrences[lemma]
                ],
            }
        )
    candidates.sort(key=lambda item: (-item["score"], -item["count"], item["lemma"]))

    profile = {
        "schema_version": LEXICAL_SCHEMA_VERSION,
        "language": language,
        "total_tokens": total_tokens,
        "distinct_lemmas": len(counts),
        "type_token_ratio": round(len(counts) / total_tokens, 6) if total_tokens else 0.0,
        "frequency_bands": dict(sorted(bands.items())),
        "selection_policy": LEXICAL_PROCESSOR_VERSION,
        "provenance": lexical_runtime_signature(language),
    }
    useful_words = {
        "schema_version": LEXICAL_SCHEMA_VERSION,
        "language": language,
        "title": f"{limit} useful words from this book",
        "selection_policy": LEXICAL_PROCESSOR_VERSION,
        "provenance": lexical_runtime_signature(language),
        "requested_limit": limit,
        "words": candidates[:limit],
    }
    return profile, useful_words
