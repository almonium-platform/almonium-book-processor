"""Chapter titles a source shouts in capitals, set in the case a reader expects.

English titles are title-cased. Other languages write titles in sentence case, where only
the first word and proper names keep a capital; a shouted title cannot say which words
are names, so the book's own text decides: a word it writes capitalised in mid-sentence
more often than not is a name, and keeps the form the text gives it.
"""

from __future__ import annotations

import re
from collections import Counter

ROMAN = re.compile(r"^[IVXLCDM]+$")
WORD = re.compile(r"\w[\w'’-]*\w|\w")
# Articles, conjunctions and short prepositions stay lower case inside an English title.
MINOR_WORDS = {
    "a",
    "an",
    "and",
    "as",
    "at",
    "but",
    "by",
    "for",
    "from",
    "in",
    "into",
    "nor",
    "of",
    "on",
    "or",
    "over",
    "the",
    "to",
    "upon",
    "with",
}
SENTENCE_END = set('.!?…:;«»"“”„—–-([')


def _shouted(text: str) -> bool:
    letters = [ch for ch in text if ch.isalpha()]
    return bool(letters) and all(ch.isupper() for ch in letters)


def proper_names(texts) -> dict[str, str]:
    """Each word the text capitalises in mid-sentence more often than not, by lower case."""

    capital: Counter = Counter()
    lower: Counter = Counter()
    forms: dict[str, Counter] = {}
    for text in texts:
        for match in WORD.finditer(text):
            word = match.group()
            before = text[: match.start()].rstrip()[-1:]
            if not before or before in SENTENCE_END:
                continue
            key = word.lower()
            if word[0].isupper() and not word.isupper():
                capital[key] += 1
                forms.setdefault(key, Counter())[word] += 1
            elif word.islower():
                lower[key] += 1
    return {key: forms[key].most_common(1)[0][0] for key in capital if capital[key] > lower[key]}


def edition_names(edition) -> dict[str, str]:
    names = getattr(edition, "_proper_names", None)
    if names is None:
        names = proper_names(edition.blocks.values_list("text", flat=True).iterator())
        edition._proper_names = names
    return names


def display_title(value: str, edition=None) -> str:
    text = (value or "").strip().rstrip(".")
    if not _shouted(text):
        return text
    language = getattr(edition, "language", "en") or "en"
    if language == "en":
        words, first = [], True
        for word in text.split():
            bare = word.rstrip(",;:.")
            if ROMAN.match(bare):
                words.append(word)
            elif not first and bare.lower() in MINOR_WORDS:
                words.append(word.lower())
            else:
                words.append(word.capitalize())
            first = word.endswith((".", ":", "!", "?"))
        return " ".join(words)
    names = edition_names(edition)
    words, first = [], True
    for word in text.split():
        bare = word.rstrip(",;:.")
        if ROMAN.match(bare):
            words.append(word)
        elif bare.lower() in names:
            words.append(names[bare.lower()] + word[len(bare) :])
        elif first:
            words.append(word.lower().capitalize())
        else:
            words.append(word.lower())
        first = word.endswith((".", "!", "?"))
    return " ".join(words)


def short_title(title: str) -> str:
    """The part of a title before its first full stop: "Розділ V" of "Розділ V. Трагедія …"."""

    head, dot, rest = title.partition(". ")
    return head if dot and rest else title
