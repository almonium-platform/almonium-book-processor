from __future__ import annotations

import sys

import pytest

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


class LemmaPipeline(FakePipeline):
    """A pipeline whose lemmas are set by a caller-supplied map."""

    def __init__(self, lemmas: dict[str, str]) -> None:
        self.lemmas = lemmas

    def __call__(self, text: str):
        tokens = super().__call__(text)
        for token in tokens:
            token.lemma_ = self.lemmas.get(token.text.casefold(), token.text.casefold())
        return tokens


def test_a_common_word_is_excluded_even_when_its_lemma_is_rare(monkeypatch) -> None:
    """The reader meets "gone", so "gone" decides the verdict, not its lemma."""

    monkeypatch.setattr(
        lexical, "_lexical_pipeline", lambda language: LemmaPipeline({"gone": "gan"})
    )
    monkeypatch.setattr(lexical, "lexical_runtime_signature", lambda language: {"test": True})
    frequencies = {"gan": 3.07, "gone": 5.17}

    _, useful = analyze_lexicon(
        [
            LexicalBlock("c1.p1", 1, "we would have gone on"),
            LexicalBlock("c2.p1", 2, "the winter had gone"),
        ],
        "en",
        frequency_lookup=lambda word, language: frequencies.get(word, 3.5),
    )

    assert [item["display"] for item in useful["words"]] == []


def test_a_fallback_lemma_far_rarer_than_its_surface_is_discarded(monkeypatch) -> None:
    monkeypatch.setattr(
        lexical, "_lexical_pipeline", lambda language: LemmaPipeline(dict.fromkeys(["gone"], ""))
    )
    monkeypatch.setattr(lexical, "lexical_runtime_signature", lambda language: {"test": True})
    frequencies = {"gan": 2.0, "gone": 3.5}

    _, useful = analyze_lexicon(
        [
            LexicalBlock("c1.p1", 1, "we would have gone on"),
            LexicalBlock("c2.p1", 2, "the winter had gone"),
        ],
        "en",
        frequency_lookup=lambda word, language: frequencies.get(word, 5.8),
        fallback_lemmatizer=lambda word, language: "gan",
    )

    assert [item["lemma"] for item in useful["words"]] == ["gone"]


def test_a_plausible_fallback_lemma_is_kept(monkeypatch) -> None:
    monkeypatch.setattr(
        lexical, "_lexical_pipeline", lambda language: LemmaPipeline(dict.fromkeys(["frozen"], ""))
    )
    monkeypatch.setattr(lexical, "lexical_runtime_signature", lambda language: {"test": True})
    frequencies = {"freeze": 4.0, "frozen": 4.32}

    _, useful = analyze_lexicon(
        [
            LexicalBlock("c1.p1", 1, "we were frozen"),
            LexicalBlock("c2.p1", 2, "the ground was frozen"),
        ],
        "en",
        frequency_lookup=lambda word, language: frequencies.get(word, 5.8),
        fallback_lemmatizer=lambda word, language: "freeze",
    )

    assert [item["lemma"] for item in useful["words"]] == ["freeze"]


def test_a_missing_model_stops_the_analysis_instead_of_guessing(monkeypatch) -> None:
    class FakeSpacy:
        @staticmethod
        def load(name: str, exclude: list[str] | None = None):
            raise OSError(f"Can't find model '{name}'")

        @staticmethod
        def blank(language: str):  # pragma: no cover - a blank pipeline must never be used
            raise AssertionError("Vocabulary analysis must not fall back to a blank pipeline")

    monkeypatch.setitem(sys.modules, "spacy", FakeSpacy)
    lexical._lexical_pipeline.cache_clear()
    try:
        with pytest.raises(lexical.LexicalModelUnavailable, match="en_core_web_sm"):
            lexical._lexical_pipeline("en")
    finally:
        lexical._lexical_pipeline.cache_clear()


def test_an_unconfigured_language_stops_the_analysis(monkeypatch) -> None:
    monkeypatch.setitem(sys.modules, "spacy", object())
    monkeypatch.setattr(lexical.settings, "NLP_SPACY_MODELS", {"en": "en_core_web_sm"})
    lexical._lexical_pipeline.cache_clear()
    try:
        with pytest.raises(lexical.LexicalModelUnavailable, match="No spaCy model is configured"):
            lexical._lexical_pipeline("sv")
    finally:
        lexical._lexical_pipeline.cache_clear()
