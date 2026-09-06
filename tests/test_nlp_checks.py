from __future__ import annotations

import sys

from almonium_book_processor.processing.checks import check_spacy_models


class FakePipeline:
    def __init__(self, pipe_names: list[str]) -> None:
        self.pipe_names = pipe_names


def _fake_spacy(pipelines: dict[str, FakePipeline]):
    class FakeSpacy:
        @staticmethod
        def load(name: str, exclude: list[str] | None = None) -> FakePipeline:
            try:
                return pipelines[name]
            except KeyError as error:
                raise OSError(f"Can't find model '{name}'") from error

    return FakeSpacy


def test_check_reports_a_missing_model(monkeypatch) -> None:
    monkeypatch.setattr(
        "django.conf.settings.NLP_SPACY_MODELS", {"en": "en_core_web_sm"}, raising=False
    )
    monkeypatch.setitem(sys.modules, "spacy", _fake_spacy({}))

    messages = check_spacy_models(None)

    assert [message.id for message in messages] == ["processing.E001"]


def test_check_reports_a_model_that_cannot_lemmatize(monkeypatch) -> None:
    monkeypatch.setattr(
        "django.conf.settings.NLP_SPACY_MODELS", {"en": "en_core_web_sm"}, raising=False
    )
    monkeypatch.setitem(
        sys.modules, "spacy", _fake_spacy({"en_core_web_sm": FakePipeline(["tok2vec", "tagger"])})
    )

    messages = check_spacy_models(None)

    assert [message.id for message in messages] == ["processing.E002"]


def test_check_passes_for_a_model_with_a_lemmatizer(monkeypatch) -> None:
    monkeypatch.setattr(
        "django.conf.settings.NLP_SPACY_MODELS", {"en": "en_core_web_sm"}, raising=False
    )
    monkeypatch.setitem(
        sys.modules,
        "spacy",
        _fake_spacy({"en_core_web_sm": FakePipeline(["tok2vec", "tagger", "lemmatizer"])}),
    )

    assert check_spacy_models(None) == []


def test_check_says_so_when_the_worker_stack_is_absent(monkeypatch) -> None:
    monkeypatch.setitem(sys.modules, "spacy", None)

    messages = check_spacy_models(None)

    assert [message.id for message in messages] == ["processing.I001"]
