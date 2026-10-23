import pytest

from almonium_book_processor.ai.output_language import (
    OutputLanguageError,
    _identifier,
    validate_output_language,
    validate_rewritten_language,
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


@pytest.mark.parametrize(
    "text,language",
    [
        ("Зневажливе слово для бездомних або неслухняних людей.", "uk"),
        ("Це її рішення.", "uk"),
        ("Это её решение.", "ru"),
    ],
)
def test_short_ukrainian_russian_and_retained_rejected_gloss(text, language):
    validate_output_language([text], language)


def test_one_ukrainian_letter_cannot_disguise_english():
    with pytest.raises(OutputLanguageError):
        validate_output_language([EN + " і"], "uk")


def test_mixed_ukrainian_and_russian_markers_are_rejected():
    with pytest.raises(OutputLanguageError):
        validate_output_language([UK + " Это её решение."], "uk")


def test_rewritten_prose_is_judged_together_once_there_is_enough_of_it():
    validate_rewritten_language(["Before dawn, he left."], "uk")  # too short to judge
    validate_rewritten_language([], "uk")
    validate_rewritten_language([UK], "uk")
    validate_rewritten_language(["He was afraid.", "Before dawn, he left, and it was cold."], "en")
    with pytest.raises(OutputLanguageError, match="uk"):
        validate_rewritten_language([EN], "uk")
    with pytest.raises(OutputLanguageError, match="uk"):
        validate_rewritten_language(["Він вийшов.", EN], "uk")


def test_a_short_field_in_a_latin_script_language_is_judged_with_the_rest_not_alone():
    # the detector takes each of these plain English glosses for another language
    glosses = [
        "Financial protection against specified losses or damage.",
        "An explicit cause-and-effect construction supports comprehension.",
    ]

    validate_output_language([EN, *glosses], "en")


def test_a_long_field_in_the_wrong_language_is_still_rejected():
    german = (
        "Der Reisende schreibt seiner Schwester von seinen Hoffnungen und Vorbereitungen vor "
        "einer ehrgeizigen Fahrt in den Norden und erklärt, warum er sie unternimmt."
    )

    with pytest.raises(OutputLanguageError):
        validate_output_language([EN, EN, german], "en")


def test_a_title_page_set_in_capitals_is_not_judged():
    # Candide's title page, translated: names, an address and roman numerals, read as French
    # (and once as Lao) by the detector however it is reworded.
    page = [
        "WORKS\nOF\nVOLTAIRE.",
        "VOLUME XXXIII",
        "PREFACES, NOTICES, NOTES, ETC.\nBY M. BEUCHOT.",
        "PARIS,\nLEFÈVRE, BOOKSELLER,\nRUE DE L'ÉPERON, No 6.",
        "MDCCCXXIX.",
    ]
    validate_output_language(page, "en")
    # the same words as prose are still held to the gate
    with pytest.raises(OutputLanguageError):
        validate_output_language(
            [
                "Les œuvres de Voltaire furent imprimées à Paris chez Lefèvre, "
                "libraire rue de l'Éperon."
            ],
            "en",
        )


def test_a_quotation_in_a_third_language_is_kept_when_the_source_is_named():
    english = [
        "The old man looked up from the book he had been reading by the window all afternoon.",
        "He read the verse aloud, slowly, as he had learned it as a boy at the seminary school.",
        "Beati pauperes spiritu, quoniam ipsorum est regnum caelorum; beati mites, quoniam "
        "ipsi possidebunt terram; beati qui lugent, quoniam ipsi consolabuntur.",
        "Then he closed the book and sat for a while without speaking to anyone in the house.",
    ]
    # the Latin verse alone reads as Italian or Latin, and without a source named it fails
    with pytest.raises(OutputLanguageError, match="sample 1"):
        validate_output_language(english, "en")
    validate_output_language(english, "en", source_language="es")
    # a field left in the source language is still refused
    untranslated = english[:2] + [
        "El anciano cerró el libro y se quedó un rato sin hablar con nadie de la casa, "
        "mirando por la ventana la plaza vacía del pueblo."
    ]
    with pytest.raises(OutputLanguageError, match="es"):
        validate_output_language(untranslated, "en", source_language="es")


def test_one_short_correction_in_a_romance_language_is_not_judged_alone():
    # the fidelity audit of Candide B1 failed on this one correction, read as Catalan at 0.39
    validate_rewritten_language(["Madame a des moyadors (des pièces d’or) et des diamants"], "fr")
    # the same length in Cyrillic is enough to tell Ukrainian from anything else
    with pytest.raises(OutputLanguageError):
        validate_rewritten_language(
            ["Мадам имеет золотые монеты и бриллианты, спрятанные в платье."], "uk"
        )
    # and a longer correction in the wrong language is still refused
    with pytest.raises(OutputLanguageError):
        validate_rewritten_language(
            [
                "La señora tiene monedas de oro y diamantes escondidos en el vestido, y espera "
                "la noche para marcharse con el viejo soldado sin que nadie la vea."
            ],
            "fr",
        )


def test_riksmaal_read_as_danish_passes_for_a_norwegian_book(monkeypatch):
    # Undset's Jenny (1911) was refused at "detected da, confidence 0.907": the detectors read
    # Riksmål as Danish, which for a Norwegian book of that day is the same written language.
    from almonium_book_processor.ai import output_language

    monkeypatch.setattr(output_language, "_classify", lambda text, expected: ("da", 0.907))
    validate_output_language(
        ["Hun gik langsomt opover Via Condotti i den stille søndagsformiddag."], "no"
    )
    with pytest.raises(OutputLanguageError):
        validate_output_language(
            ["Hun gik langsomt opover Via Condotti i den stille søndagsformiddag."], "sv"
        )


def test_danish_prose_split_between_danish_and_norwegian_passes_for_a_danish_book(monkeypatch):
    # Ved Vejen's B2 was refused at "detected da, confidence 0.547": the detectors split Danish
    # between da and no, so for either language of that pair the split is not a doubt.
    from almonium_book_processor.ai import output_language

    monkeypatch.setattr(output_language, "_classify", lambda text, expected: ("da", 0.547))
    validate_output_language(["Hun gik langsomt op ad vejen i den stille formiddag."], "da")
    monkeypatch.setattr(output_language, "_classify", lambda text, expected: ("no", 0.5))
    validate_output_language(["Hun gik langsomt op ad vejen i den stille formiddag."], "da")
    monkeypatch.setattr(output_language, "_classify", lambda text, expected: ("sv", 0.5))
    with pytest.raises(OutputLanguageError):
        validate_output_language(["Hun gik langsomt op ad vejen i den stille formiddag."], "da")
