"""Language registry shared by ingestion, the admin UI, and the API."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class LanguageDefinition:
    code: str
    name: str
    aliases: tuple[str, ...] = ()


# Keep this list as the single catalogue of languages that can be selected for
# a book. Values are ISO 639-1 codes; aliases cover common EPUB/TEI variants.
LANGUAGES = (
    LanguageDefinition("bg", "Bulgarian"),
    LanguageDefinition("ca", "Catalan"),
    LanguageDefinition("cs", "Czech"),
    LanguageDefinition("da", "Danish"),
    LanguageDefinition("de", "German", ("deu", "ger")),
    LanguageDefinition("el", "Greek", ("ell", "gre")),
    LanguageDefinition("en", "English", ("eng",)),
    LanguageDefinition("es", "Spanish", ("spa",)),
    LanguageDefinition("et", "Estonian"),
    LanguageDefinition("fi", "Finnish"),
    LanguageDefinition("fr", "French", ("fra", "fre")),
    LanguageDefinition("ga", "Irish"),
    LanguageDefinition("hr", "Croatian", ("hrv",)),
    LanguageDefinition("hu", "Hungarian", ("hun",)),
    LanguageDefinition("is", "Icelandic", ("isl", "ice")),
    LanguageDefinition("it", "Italian", ("ita",)),
    LanguageDefinition("lt", "Lithuanian"),
    LanguageDefinition("lv", "Latvian"),
    LanguageDefinition("mt", "Maltese"),
    LanguageDefinition("nl", "Dutch", ("nld", "dut")),
    LanguageDefinition("no", "Norwegian", ("nor", "nb", "nn")),
    LanguageDefinition("pl", "Polish", ("pol",)),
    LanguageDefinition("pt", "Portuguese", ("por",)),
    LanguageDefinition("ro", "Romanian", ("ron", "rum")),
    LanguageDefinition("ru", "Russian", ("rus",)),
    LanguageDefinition("sk", "Slovak", ("slk", "slo")),
    LanguageDefinition("sl", "Slovenian", ("slv",)),
    LanguageDefinition("sr", "Serbian", ("srp",)),
    LanguageDefinition("sv", "Swedish", ("swe",)),
    LanguageDefinition("tr", "Turkish", ("tur",)),
    LanguageDefinition("uk", "Ukrainian", ("ukr",)),
)

LANGUAGE_CHOICES = tuple(
    (language.code, f"{language.name} ({language.code})") for language in LANGUAGES
)
LANGUAGE_CODES = frozenset(language.code for language in LANGUAGES)
LANGUAGE_ALIASES = {alias: language.code for language in LANGUAGES for alias in language.aliases}


def normalize_language_code(value: object) -> str:
    """Return the canonical ISO 639-1 code for a source language value."""

    if not isinstance(value, str):
        raise ValueError("Language code must be text")
    normalized = value.strip().lower().replace("_", "-").split("-", 1)[0]
    canonical = LANGUAGE_ALIASES.get(normalized, normalized)
    if canonical not in LANGUAGE_CODES:
        raise ValueError(f"Unsupported language code: {value}")
    return canonical
