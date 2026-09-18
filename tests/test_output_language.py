import pytest

from almonium_book_processor.ai.output_language import (
    OutputLanguageError,
    _identifier,
    validate_output_language,
)
from almonium_book_processor.languages import LANGUAGE_CODES

UK = "Молодий науковець створює живу істоту й покидає її. Він боїться наслідків свого вчинку."
EN = "A young scientist creates a living being and abandons it. He fears the consequences."
RU = "Молодой учёный создаёт живое существо и покидает его. Он боится последствий своего поступка."


def test_detector_covers_every_catalogue_language():
    assert set(_identifier().nb_classes) >= LANGUAGE_CODES


@pytest.mark.parametrize("text,language", [(UK, "uk"), (EN, "en"), (RU, "ru")])
def test_accepts_actual_language_deterministically(text, language):
    for _ in range(3):
        validate_output_language([text], language)


@pytest.mark.parametrize("texts", [[EN], [RU], [UK * 10, EN]])
def test_rejects_english_russian_and_mixed_ukrainian_output(texts):
    with pytest.raises(OutputLanguageError, match="uk"):
        validate_output_language(texts, "uk")
