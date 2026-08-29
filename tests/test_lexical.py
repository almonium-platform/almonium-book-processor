from __future__ import annotations

from almonium_book_processor.processing import lexical
from almonium_book_processor.processing.lexical import LexicalBlock, analyze_lexicon


class FakeToken:
    def __init__(self, text: str, idx: int, *, stop: bool = False, pos: str = "NOUN") -> None:
        self.text = text
        self.idx = idx
        self.lemma_ = text.casefold()
        self.is_alpha = text.isalpha()
        self.is_stop = stop
        self.pos_ = pos


class FakePipeline:
    def __call__(self, text: str):
        tokens = []
        offset = 0
        for raw in text.split():
            surface = raw.strip(".,;:!?")
            idx = text.index(surface, offset)
            offset = idx + len(surface)
            tokens.append(FakeToken(surface, idx, stop=surface.casefold() in {"the", "and", "a"}))
        return tokens


def test_lexical_profile_and_useful_words_are_deterministic(monkeypatch) -> None:
    monkeypatch.setattr(lexical, "_lexical_pipeline", lambda language: FakePipeline())
    monkeypatch.setattr(lexical, "lexical_runtime_signature", lambda language: {"test": True})
    frequencies = {"lantern": 3.0, "harbor": 4.5, "voyage": 3.8, "ordinary": 5.0}
    blocks = [
        LexicalBlock("c1.p1", 1, "The lantern lantern watched the harbor."),
        LexicalBlock("c2.p1", 2, "Lantern and harbor began a voyage."),
    ]

    profile, useful = analyze_lexicon(
        blocks,
        "en",
        frequency_lookup=lambda word, language: frequencies.get(word, 5.8),
    )

    assert profile["total_tokens"] == 12
    assert profile["distinct_lemmas"] == 8
    assert profile["frequency_bands"]["uncommon"] == 4
    assert [item["lemma"] for item in useful["words"]] == ["lantern", "harbor"]
    assert useful["words"][0]["chapter_count"] == 2
    assert useful["words"][0]["occurrences"][0]["block_id"] == "c1.p1"


def test_useful_words_exclude_hapaxes_stop_words_and_proper_nouns(monkeypatch) -> None:
    class FilteringPipeline(FakePipeline):
        def __call__(self, text: str):
            tokens = super().__call__(text)
            for token in tokens:
                if token.text == "Gregor":
                    token.pos_ = "PROPN"
            return tokens

    monkeypatch.setattr(lexical, "_lexical_pipeline", lambda language: FilteringPipeline())
    monkeypatch.setattr(lexical, "lexical_runtime_signature", lambda language: {"test": True})
    _, useful = analyze_lexicon(
        [LexicalBlock("c1.p1", 1, "Gregor Gregor the the metamorphosis singular")],
        "en",
        frequency_lookup=lambda word, language: 3.5,
    )

    assert useful["words"] == []
