from types import SimpleNamespace

import pytest

from almonium_book_processor.processing.punctuation import fold_punctuation, is_punctuation_only
from almonium_book_processor.processing.sentence_correspondence import sentence_texts


def spans_of(text: str, pieces: list[str]) -> list[dict]:
    """Spans for pieces found in order in text, as spaCy would have cut them."""

    spans, cursor = [], 0
    for piece in pieces:
        start = text.index(piece, cursor)
        spans.append({"start": start, "end": start + len(piece)})
        cursor = start + len(piece)
    return spans


def folded(text: str, pieces: list[str], language: str) -> list[str]:
    result = fold_punctuation(text, spans_of(text, pieces), language)
    # The text is still covered exactly: only whitespace between spans, nothing dropped.
    sentence_texts(SimpleNamespace(text=text, sentences=result))
    return [text[s["start"] : s["end"]] for s in result]


def test_a_french_quote_keeps_its_guillemets():
    text = "« Alors, Josef, commença l'oncle. » Il se tut."
    pieces = ["«", "Alors, Josef, commença l'oncle.", "»", "Il se tut."]
    assert folded(text, pieces, "fr") == ["« Alors, Josef, commença l'oncle. »", "Il se tut."]


def test_a_dialogue_dash_opens_the_reply():
    text = "Il entra. — Non, dit K. en se levant."
    pieces = ["Il entra.", "—", "Non, dit K. en se levant."]
    assert folded(text, pieces, "fr") == ["Il entra.", "— Non, dit K. en se levant."]
    assert folded("— Sì, disse.", ["—", "Sì, disse."], "it") == ["— Sì, disse."]


def test_german_guillemets_point_inward():
    text = "»Guten Tag.« Er ging."
    assert folded(text, ["»Guten Tag.", "«", "Er ging."], "de") == ["»Guten Tag.«", "Er ging."]
    # Set apart by spaces, the language decides: » opens in German and closes in French.
    text = "Er sagte » Halt « und ging."
    assert folded(text, ["Er sagte", "»", "Halt", "«", "und ging."], "de") == [
        "Er sagte",
        "» Halt «",
        "und ging.",
    ]
    text = "Il dit « Halte » et partit."
    assert folded(text, ["Il dit", "«", "Halte", "»", "et partit."], "fr") == [
        "Il dit",
        "« Halte »",
        "et partit.",
    ]


def test_a_scene_break_and_trailing_marks_join_what_came_before():
    text = "Er ging. * * * Sie kam."
    assert folded(text, ["Er ging.", "* * *", "Sie kam."], "de") == ["Er ging. * * *", "Sie kam."]
    text = "Il partit. »"
    assert folded(text, ["Il partit.", "»"], "fr") == ["Il partit. »"]


def test_marks_in_a_row_go_with_the_sentence_they_open():
    text = "Fin. — « Oui, dit-il. »"
    pieces = ["Fin.", "—", "«", "Oui, dit-il.", "»"]
    assert folded(text, pieces, "fr") == ["Fin.", "— « Oui, dit-il. »"]


def test_a_block_of_marks_alone_stays_one_span_and_folding_twice_changes_nothing():
    assert folded("* * *", ["* * *"], "en") == ["* * *"]
    assert folded("— —", ["—", "—"], "fr") == ["— —"]
    text = "« Alors, Josef. » Il se tut."
    once = fold_punctuation(text, spans_of(text, ["«", "Alors, Josef.", "»", "Il se tut."]), "fr")
    assert fold_punctuation(text, once, "fr") == once


@pytest.mark.parametrize(
    ("piece", "only"),
    [("«", True), ("— »", True), ("* * *", True), ("Oui.", False), ("« Oui", False), ("  ", False)],
)
def test_what_counts_as_punctuation_only(piece, only):
    assert is_punctuation_only(piece) is only
