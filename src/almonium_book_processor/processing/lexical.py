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

# Everyday vocabulary a learner already has; the gate and the band label it
# the same way, so nothing the list calls "very common" can be picked.
VERY_COMMON_ZIPF = 5.0
# Below this a word is usually a name, OCR damage, or too obscure to be worth
# one of the fifty slots.
OBSCURE_ZIPF = 2.5

# A fallback lemma this much rarer than the surface it came from is mangled
# (simplemma turns the English "gone" into "gan"), not a lemma worth keeping.
MAX_FALLBACK_LEMMA_FREQUENCY_DROP = 1.0


class LexicalModelUnavailable(RuntimeError):
    """No trustworthy lemmatizer exists for the language, so we refuse to guess.

    A blank spaCy pipeline tokenizes but does not lemmatize or tag, which turns
    every filter here into a filter on a made-up word. Failing is the only
    honest option: a silent fallback shipped "gone" as an uncommon word.
    """


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
    if not model_name:
        raise LexicalModelUnavailable(
            f"No spaCy model is configured for {language!r}. "
            "Add one to NLP_SPACY_MODELS before analyzing this language."
        )
    try:
        return spacy.load(model_name, exclude=["ner"])
    except OSError as error:
        raise LexicalModelUnavailable(
            f"The spaCy model {model_name!r} for {language!r} is not installed. "
            "Install it in the image rather than falling back to a blank pipeline."
        ) from error


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
    if zipf >= VERY_COMMON_ZIPF:
        return "very_common"
    if zipf >= 4:
        return "common"
    if zipf >= 3:
        return "uncommon"
    return "rare"


def _fallback_lemma(word: str, language: str) -> str:
    try:
        import simplemma
    except ImportError as error:
        message = "Install the worker dependency group to lemmatize vocabulary"
        raise RuntimeError(message) from error
    try:
        return simplemma.lemmatize(word, lang=language)
    except ValueError:
        return word


def _lemma(
    token: Any,
    language: str,
    *,
    frequency_lookup: Callable[[str, str], float],
    fallback_lemmatizer: Callable[[str, str], str],
) -> str:
    """Lemmatize a token, distrusting the fallback when it invents a rare word."""

    surface = token.text.casefold().strip()
    if token.lemma_:
        return token.lemma_.casefold().strip() or surface

    candidate = fallback_lemmatizer(token.text, language).casefold().strip()
    if not candidate or candidate == surface:
        return surface
    drop = frequency_lookup(surface, language) - frequency_lookup(candidate, language)
    if drop > MAX_FALLBACK_LEMMA_FREQUENCY_DROP:
        return surface
    return candidate


def _looks_like_proper_name(text: str, token: Any, language: str) -> bool:
    if token.pos_ == "PROPN":
        return True
    if language == "de" or not token.text[:1].isupper():
        return False
    before = text[: token.idx].rstrip().rstrip("\"'“”«»„([{—–")
    return bool(before) and before[-1] not in ".!?…"


def lexical_runtime_signature(language: str) -> dict[str, Any]:
    pipeline = _lexical_pipeline(language)
    model_name = f"{pipeline.meta.get('lang', 'xx')}_{pipeline.meta.get('name', 'unknown')}"
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
    fallback_lemmatizer: Callable[[str, str], str] = _fallback_lemma,
    limit: int = USEFUL_WORD_LIMIT,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Build book-level lexical statistics and a useful distinctive-word list.

    Selection is deterministic. It rewards repeated, chapter-dispersed lemmas
    that are uncommon in general language, while excluding stop words, proper
    nouns, hapaxes, and extremely obscure forms that are usually names, OCR
    damage, or poor learning targets.

    Rarity is judged on the whole entry - the lemma and every surface form the
    reader actually meets - because a common word behind a rarer lemma is still
    a common word, and picking it would waste one of the fifty slots.
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
            lemma = _lemma(
                token,
                language,
                frequency_lookup=frequency_lookup,
                fallback_lemmatizer=fallback_lemmatizer,
            )
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

    lemma_frequencies = {lemma: frequency_lookup(lemma, language) for lemma in counts}
    frequencies = {
        lemma: max(
            lemma_frequencies[lemma],
            *(frequency_lookup(surface.casefold(), language) for surface in surfaces[lemma]),
        )
        for lemma in counts
    }
    bands = Counter()
    for lemma, count in counts.items():
        bands[_frequency_band(frequencies[lemma])] += count

    candidates = []
    chapter_total = len({item.chapter for item in blocks})
    for lemma, count in counts.items():
        zipf = frequencies[lemma]
        if lemma in excluded or count < 2 or not OBSCURE_ZIPF <= zipf < VERY_COMMON_ZIPF:
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
                "lemma_zipf_frequency": round(lemma_frequencies[lemma], 3),
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
