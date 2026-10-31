"""A paragraph larger than a judge's window is read in sentence pieces, never truncated."""

import pytest

from almonium_book_processor.catalog.chapter_analysis import (
    _json,
    _verify_citations,
    fitted_blocks,
    window_parts,
)
from almonium_book_processor.catalog.pilot_difficulty import windows_of

WINDOW = 600


def _long_paragraph(sentences: int) -> dict:
    text = " ".join(f"K. sah den Advokaten an, Satz {n} war lang genug." for n in range(sentences))
    return {"block_id": "c5.p4", "text": text, "type": "paragraph"}


def test_blocks_that_fit_pass_untouched():
    blocks = [{"block_id": "c1.p1", "text": "Kurz.", "type": "paragraph"}]

    assert fitted_blocks(blocks, WINDOW) is not blocks
    assert fitted_blocks(blocks, WINDOW) == blocks
    assert window_parts(blocks, WINDOW) == [blocks]


def test_a_long_paragraph_is_cut_at_sentence_ends_into_exact_slices():
    block = _long_paragraph(60)

    pieces = fitted_blocks([block], WINDOW)

    assert len(pieces) > 1
    for index, piece in enumerate(pieces, 1):
        assert piece["block_id"] == "c5.p4"
        assert (piece["part"], piece["parts"]) == (index, len(pieces))
        assert block["text"][piece["offset"] :].startswith(piece["text"])
        assert piece["text"].endswith(".")
        assert len(_json([piece]).encode()) <= WINDOW
    assert " ".join(piece["text"] for piece in pieces) == block["text"]


def test_no_window_holds_two_pieces_of_one_paragraph():
    blocks = [_long_paragraph(60), {"block_id": "c5.p5", "text": "Dann.", "type": "paragraph"}]

    for window in window_parts(blocks, WINDOW) + windows_of(blocks, WINDOW):
        ids = [block["block_id"] for block in window]
        assert len(ids) == len(set(ids))


def test_a_sentence_longer_than_a_window_is_refused():
    block = {"block_id": "c1.p1", "text": "wort " * 400, "type": "paragraph"}

    with pytest.raises(ValueError, match="No text was truncated"):
        fitted_blocks([block], WINDOW)


def test_a_citation_in_a_later_piece_points_into_the_whole_paragraph():
    from almonium_book_processor.ai.chapter_analysis import ChapterAnalysis

    block = _long_paragraph(60)
    piece = fitted_blocks([block], WINDOW)[-1]
    quote = piece["text"][:40]
    from almonium_book_processor.ai.chapter_analysis import Evidence

    evidence = Evidence(
        block_id="c5.p4", quote=quote, dimension="syntax", explanation="Long clauses."
    )
    result = ChapterAnalysis.model_construct(
        evidence=[evidence], hard_words=[], themes=[], characters=[], content_flags=[]
    )

    _, spans, _ = _verify_citations(result, {"blocks": [piece]})

    start, end = spans[0]["start"], spans[0]["end"]
    assert block["text"][start:end] == quote
