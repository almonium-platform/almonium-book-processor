"""Quotation and dialogue marks by language, and the "sentences" that are only marks.

spaCy's small models place sentence boundaries with the parser, and they give an opening
guillemet, a closing one or a dialogue dash a sentence of its own. In the library on
18 November 2026, 14.3% of French sentences were a lone «, » or —, 23.7% of Italian ones
and 7.8% of Portuguese ones a dialogue dash, and 1-4% in Danish, Dutch, Greek, Norwegian
and Polish. A reader was offered a quote mark as a sentence, and the aligner a piece with
no meaning to match. :func:`fold_punctuation` joins every such piece to the sentence it
belongs to; the text and every other boundary stay as they were.

Which way a mark belongs is a property of the language: German and Danish set »…« with
the points inward, so » opens a quote there and closes one in French; German closes „…“
with the mark English opens with. Swedish and Finnish use » and ” on both sides, so there
the side a mark touches without a space decides.
"""

from __future__ import annotations

import re

_WORD = re.compile(r"\w")

# Marks that open what follows. Everything else a punctuation-only piece is made of closes
# what came before, unless the language uses it on both sides.
_OPENING = {
    "default": set("«„“‘‚‹¿¡([{"),
    "de": set("»„‚›([{"),
    "da": set("»„‚›([{"),
    "sv": set("([{"),
    "fi": set("([{"),
}
_CLOSING = {
    "default": set("»”’›)]}"),
    "de": set("«“‘‹)]}"),
    "da": set("«“‘‹)]}"),
    "sv": set(")]}"),
    "fi": set(")]}"),
}
# A dash alone starts a reply ("— Non, dit K.") or a dashed aside: it opens what follows.
_DASHES = set("—–―-")


def opening_marks(language: str) -> set[str]:
    return _OPENING.get(language, _OPENING["default"])


def closing_marks(language: str) -> set[str]:
    return _CLOSING.get(language, _CLOSING["default"])


def is_punctuation_only(piece: str) -> bool:
    return bool(piece.strip()) and not _WORD.search(piece)


def _side(text: str, spans: list[dict], index: int, language: str) -> str:
    """'next' or 'previous': the sentence a punctuation-only piece belongs to."""

    span = spans[index]
    has_previous, has_next = index > 0, index < len(spans) - 1
    # A mark set against text without a space belongs to that text: »Guten Tag.« ...
    touches_previous = has_previous and spans[index - 1]["end"] == span["start"]
    touches_next = has_next and spans[index + 1]["start"] == span["end"]
    if touches_next and not touches_previous:
        return "next"
    if touches_previous and not touches_next:
        return "previous"
    marks = set(text[span["start"] : span["end"]]) - set(" \t\n  ")
    opening = opening_marks(language) | _DASHES
    if has_next and marks and marks <= opening:
        return "next"
    if has_previous and marks and marks <= closing_marks(language):
        return "previous"
    if not has_previous:
        return "next"
    return "previous"


def fold_punctuation(text: str, spans: list[dict], language: str) -> list[dict]:
    """Sentence spans with every punctuation-only piece joined to its sentence.

    Spans are ``{"start", "end"}`` offsets into ``text``, in order, with only whitespace
    between them; the result keeps that, covers the same text, and keeps every other
    boundary. A block made of marks alone keeps them as one span. Other keys of a span
    (an ``id``) are dropped: the caller numbers the result.
    """

    if len(spans) < 2:
        return [{"start": s["start"], "end": s["end"]} for s in spans]
    result: list[dict] = []
    waiting: dict | None = None  # marks that open the next sentence
    for index, span in enumerate(spans):
        piece = text[span["start"] : span["end"]]
        if not is_punctuation_only(piece):
            start = waiting["start"] if waiting else span["start"]
            result.append({"start": start, "end": span["end"]})
            waiting = None
            continue
        if waiting is None and _side(text, spans, index, language) == "previous" and result:
            result[-1]["end"] = span["end"]
        elif waiting is None:
            waiting = {"start": span["start"], "end": span["end"]}
        else:  # marks in a row that open the next sentence stay together
            waiting["end"] = span["end"]
    if waiting is not None:
        if result:
            result[-1]["end"] = waiting["end"]
        else:
            result.append(waiting)
    return result
