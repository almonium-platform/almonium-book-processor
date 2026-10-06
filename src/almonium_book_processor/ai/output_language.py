"""Offline, deterministic language gate for generated prose, never source quotations.

Language identification is statistical, not proof of fluency. Short labels and names
are ambiguous: assess short prose fields together, and longer fields separately so
an English recap cannot hide inside a Ukrainian assessment. Reject uncertainty.
"""

from functools import lru_cache

from langid.langid import LanguageIdentifier, model
from lingua import Language, LanguageDetectorBuilder

from almonium_book_processor.languages import normalize_language_code


class OutputLanguageError(ValueError):
    """Safe to record: contains no source or generated text."""


# Below this, langid's verdict on a single field is noise ("Before dawn, he left."
# scores English at 0.61), so shorter samples are only judged together.
MIN_ASSESSABLE_LETTERS = 40
# One field among several is judged on its own only when it is long enough to trust the
# verdict on it alone. Telling Ukrainian from Russian rests on the alphabet and holds for a
# phrase; telling one Latin-script language from another does not. At 48 and 57 letters the
# detector called plain English glosses Spanish ("Financial protection against specified
# losses or damage.", 0.69) and German ("An explicit cause-and-effect construction supports
# comprehension.", 0.87), and each rejection failed a whole analysis whose prose, read
# together, was English at 1.0. A field in the wrong language is rarely that short; a short
# one still counts in the text judged together.
MIN_FIELD_LETTERS = 100


@lru_cache(maxsize=1)
def _identifier():
    return LanguageIdentifier.from_modelstring(model, norm_probs=True)


@lru_cache(maxsize=1)
def _cyrillic_identifier():
    return LanguageDetectorBuilder.from_languages(
        Language.UKRAINIAN,
        Language.RUSSIAN,
        Language.BULGARIAN,
        Language.MACEDONIAN,
        Language.SERBIAN,
        Language.ENGLISH,
    ).build()


def _classify(text: str, expected: str) -> tuple[str, float]:
    if expected not in {"uk", "ru"}:
        return _identifier().classify(text)
    letters = [c.lower() for c in text if c.isalpha()]
    uk = bool(set(letters) & set("іїєґ"))
    ru = bool(set(letters) & set("ыэъё"))
    # Alphabet evidence distinguishes Ukrainian/Russian, but must not let one
    # Cyrillic word disguise a predominantly English explanation.
    cyrillic = sum("\u0400" <= c <= "\u052f" for c in letters)
    if letters and cyrillic / len(letters) >= 0.8:
        if uk and ru:
            return "mixed-uk-ru", 0.0
        if uk:
            return "uk", 1.0
        if ru:
            return "ru", 1.0
    candidates = _cyrillic_identifier().compute_language_confidence_values(text)
    first = candidates[0]
    return first.language.iso_code_639_1.name.lower(), first.value


def validate_output_language(texts: list[str], language: str) -> None:
    expected = normalize_language_code(language)
    prose = [text.strip() for text in texts if text.strip()]
    if not prose:
        return
    candidates = ["\n".join(prose)]
    if len(prose) > 1:
        minimum = MIN_ASSESSABLE_LETTERS if expected in {"uk", "ru"} else MIN_FIELD_LETTERS
        candidates += [t for t in prose if sum(c.isalpha() for c in t) >= minimum]
    for index, text in enumerate(candidates):
        detected, confidence = _classify(text, expected)
        # langid distinguishes Norwegian Bokmål and Nynorsk; the catalogue does not.
        detected = {"nb": "no", "nn": "no"}.get(detected, detected)
        # The gate is against prose in the wrong language. The whole text must be read as
        # the expected language with confidence; one block of it, short and without the
        # letters that tell Ukrainian from Russian, need only be read as that language: a
        # chapter of Wuthering Heights was refused on one such block read as Ukrainian at 0.79.
        if detected != expected or (index == 0 and confidence < 0.8):
            raise OutputLanguageError(
                f"Generated prose did not validate as {expected}: sample {index}, "
                f"detected {detected}, confidence {confidence:.3f}."
            )


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


def validate_rewritten_language(texts: list[str], language: str) -> None:
    """Gate for text written into a book: adapted blocks and audit corrections.

    Judged as one sample. Kept blocks are the source verbatim and a quotation inside
    a rewritten paragraph does not change its language, so callers pass only the
    changed text; a handful of short phrases is not enough evidence either way.
    """
    prose = "\n".join(text.strip() for text in texts if text.strip())
    if sum(c.isalpha() for c in prose) < MIN_ASSESSABLE_LETTERS:
        return
    validate_output_language([prose], language)
