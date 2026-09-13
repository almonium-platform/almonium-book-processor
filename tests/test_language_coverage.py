"""The language registry, the model map, and the pinned wheels must agree."""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

from django.conf import settings

from almonium_book_processor.languages import LANGUAGE_CODES, normalize_language_code

PYPROJECT = Path(__file__).resolve().parents[1] / "pyproject.toml"


def _pinned_spacy_models() -> set[str]:
    worker = tomllib.loads(PYPROJECT.read_text())["project"]["optional-dependencies"]["worker"]
    return {
        match.group(1)
        for requirement in worker
        if (match := re.match(r"(\w+) @ https://github.com/explosion/spacy-models/", requirement))
    }


def test_every_spacy_model_belongs_to_a_registered_language() -> None:
    assert set(settings.NLP_SPACY_MODELS) <= LANGUAGE_CODES


def test_every_configured_spacy_model_is_pinned_and_vice_versa() -> None:
    assert set(settings.NLP_SPACY_MODELS.values()) == _pinned_spacy_models()


def test_new_languages_normalize_from_their_three_letter_codes() -> None:
    assert normalize_language_code("jpn") == "ja"
    assert normalize_language_code("kor") == "ko"
    assert normalize_language_code("mkd") == "mk"
    assert normalize_language_code("cmn") == "zh"
    assert normalize_language_code("zh-Hans") == "zh"
    assert normalize_language_code("nb") == "no"
