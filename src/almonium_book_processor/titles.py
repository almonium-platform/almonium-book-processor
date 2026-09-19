"""Title and author casing, settled once where a book's metadata enters.

Sources shout titles often enough that the catalogue would otherwise mix
"Bleak House" with "FRANKENSTEIN, OU LE PROMÉTHÉE MODERNE". Ingestion, the
metadata stage and the upload forms all run their values through
:func:`calm_title`, so the stored title is the one every page prints and no
template needs to re-case it.
"""

from __future__ import annotations

import re

# Function words that stay lower-case inside a title once a shouting source
# title is calmed down. A few languages' worth is enough: the goal is to stop
# "FRANKENSTEIN, OU LE PROMÉTHÉE MODERNE" reading as a design decision, not to
# reproduce every house style.
_SMALL_WORDS = frozenset(
    # English
    ("a", "an", "the", "of", "and", "or", "nor", "but", "in", "on", "at", "to", "for", "by")
    + ("with", "from", "as")
    # French
    + ("le", "la", "les", "l", "un", "une", "des", "du", "de", "d", "et", "ou", "à", "au")
    + ("aux", "en", "sur")
    # German
    + ("der", "die", "das", "ein", "eine", "und", "oder", "von", "im", "am", "zu", "für")
    # Spanish and Italian
    + ("el", "los", "las", "y", "o", "del", "il", "lo", "gli", "e", "di", "della", "dei")
    + ("degli",)
    # Ukrainian and Russian
    + ("і", "й", "та", "або", "чи", "на", "в", "у", "з", "із", "до", "и", "или", "с", "из", "к")
)

_WORD = re.compile(r"[^\W\d_]+(?:['’][^\W\d_]+)*", re.UNICODE)
# A one-letter elision ("l'", "d'", "O'") is not the word; the word follows it.
_ELISION = re.compile(r"^([^\W\d_])(['’])([^\W\d_])", re.UNICODE)


def calm_title(title: str) -> str:
    """A source title or author as the catalogue stores it, an all-capitals one calmed.

    A value with any lower-case letter is left exactly as it came: it already
    carries its own casing, and re-casing it would only lose information.
    """

    if not title or any(character.islower() for character in title):
        return title
    lowered = title.lower()
    first_start = None
    match = _WORD.search(lowered)
    if match:
        first_start = match.start()

    def capitalise(match: re.Match[str]) -> str:
        word = match.group(0)
        if match.start() != first_start and word in _SMALL_WORDS:
            return word
        elided = _ELISION.match(word)
        if elided:
            head, apostrophe, tail = elided.groups()
            return head.upper() + apostrophe + tail.upper() + word[3:]
        return word[0].upper() + word[1:]

    return _WORD.sub(capitalise, lowered)
