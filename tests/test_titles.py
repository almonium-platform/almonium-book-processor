from __future__ import annotations

from almonium_book_processor.titles import calm_title


def test_a_shouting_title_is_calmed_and_the_rest_left_alone():
    assert calm_title("FRANKENSTEIN, OU LE PROMÉTHÉE MODERNE") == (
        "Frankenstein, ou le Prométhée Moderne"
    )
    assert calm_title("THE PICTURE OF DORIAN GRAY") == "The Picture of Dorian Gray"
    assert calm_title("LE TOUR DU MONDE EN QUATRE-VINGTS JOURS") == (
        "Le Tour du Monde en Quatre-Vingts Jours"
    )
    assert calm_title("Bleak House") == "Bleak House"
    assert calm_title("") == ""


def test_an_elision_capitalises_the_word_after_it_but_a_contraction_does_not():
    assert calm_title("L'ÉTRANGER") == "L'Étranger"
    assert calm_title("O’BRIEN") == "O’Brien"
    assert calm_title("DON'T LOOK NOW") == "Don't Look Now"


def test_an_author_keeps_a_lower_case_particle():
    assert calm_title("JULES VERNE") == "Jules Verne"
    assert calm_title("HONORÉ DE BALZAC") == "Honoré de Balzac"
