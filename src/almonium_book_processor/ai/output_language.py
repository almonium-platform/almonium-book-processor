"""Offline, deterministic language gate for generated prose, never source quotations.

Language identification is statistical, not proof of fluency. Short labels and names
are ambiguous: assess short prose fields together, and longer fields separately so
an English recap cannot hide inside a Ukrainian assessment. Reject uncertainty.
"""

from functools import lru_cache

from langid.langid import LanguageIdentifier, model

from almonium_book_processor.languages import normalize_language_code


class OutputLanguageError(ValueError):
    """Safe to record: contains no source or generated text."""


@lru_cache(maxsize=1)
def _identifier():
    return LanguageIdentifier.from_modelstring(model, norm_probs=True)


def validate_output_language(texts: list[str], language: str) -> None:
    expected = normalize_language_code(language)
    prose = [text.strip() for text in texts if text.strip()]
    if not prose:
        return
    candidates = ["\n".join(prose), *(t for t in prose if sum(c.isalpha() for c in t) >= 40)]
    for text in candidates:
        detected, confidence = _identifier().classify(text)
        # langid distinguishes Norwegian Bokmål and Nynorsk; the catalogue does not.
        detected = {"nb": "no", "nn": "no"}.get(detected, detected)
        if detected != expected or confidence < 0.8:
            raise OutputLanguageError(f"Generated prose did not validate as {expected}.")


def validate_analysis_language(result, language: str) -> None:
    validate_output_language(
        [
            result.spoiler_free_description,
            result.recap,
            result.setting,
            *result.themes,
            *result.content_flags,
            *(item.explanation for item in result.evidence),
            *(item.explanation for item in result.hard_words),
        ],
        language,
    )
