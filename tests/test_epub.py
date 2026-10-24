from __future__ import annotations

import os

import pytest
from ebooklib import epub

from almonium_book_processor.ingest.epub import ingest_epub
from almonium_book_processor.models import (
    BlockType,
    IngestionWarningSeverity,
    ingestion_warning_severity,
)


def test_epub_uses_metadata_spine_order_and_resolves_images(tmp_path) -> None:
    source = tmp_path / "book.epub"
    book = epub.EpubBook()
    book.set_identifier("urn:test:book")
    book.set_title("Spine Test")
    book.set_language("de")
    book.add_author("Ada Author")

    second = epub.EpubHtml(title="Second", file_name="text/second.xhtml", lang="de")
    second.content = "<h2>Zwei</h2><p>Der zweite Abschnitt.</p>"
    first = epub.EpubHtml(title="First", file_name="text/first.xhtml", lang="de")
    first.content = (
        '<h2 id="one">Eins</h2><p>Der erste Abschnitt.</p>'
        '<p><img src="../images/plate.jpg" alt="Bild"/></p>'
    )
    book.add_item(second)
    book.add_item(first)
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    book.spine = ["nav", first, second]
    epub.write_epub(source, book)

    artifact = ingest_epub(
        source,
        edition_slug="spine-test-de-orig",
        work_slug="spine-test",
    )

    assert artifact.edition.title == "Spine Test"
    assert artifact.edition.source.identifier == "urn:test:book"
    assert [block.text for block in artifact.blocks[:2]] == ["Eins", "Der erste Abschnitt."]
    assert artifact.blocks[2].type == BlockType.IMAGE
    assert artifact.blocks[2].source_ref == "images/plate.jpg"
    assert [block.text for block in artifact.blocks[3:]] == ["Zwei", "Der zweite Abschnitt."]
    assert [block.chapter for block in artifact.blocks] == [0, 0, 0, 1, 1]


def _cover_epub(tmp_path, *, cover_page: str, extra=()) -> str:
    """A Gutenberg-shaped EPUB: an SVG-wrapped cover page ahead of the text."""

    source = tmp_path / "cover.epub"
    book = epub.EpubBook()
    book.set_identifier("urn:test:cover")
    book.set_title("Cover Test")
    book.set_language("de")
    book.add_author("Ada Author")
    book.set_cover("cover.jpg", b"binary", create_page=False)

    wrapper = epub.EpubHtml(title="Cover", file_name="wrap0000.xhtml", lang="de")
    wrapper.content = cover_page
    chapter = epub.EpubHtml(title="One", file_name="one.xhtml", lang="de")
    chapter.content = "<h2>Eins</h2><p>Der erste Abschnitt.</p>"
    book.add_item(wrapper)
    book.add_item(chapter)
    for item in extra:
        book.add_item(item)
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    book.spine = ["nav", wrapper, *extra, chapter]
    epub.write_epub(source, book)
    return str(source)


SVG_COVER = (
    '<div class="x-ebookmaker-cover"><svg xmlns="http://www.w3.org/2000/svg" '
    'viewBox="0 0 425 672" xmlns:xlink="http://www.w3.org/1999/xlink">'
    '<image width="425" height="672" xlink:href="cover.jpg"/></svg></div>'
)


def test_declared_cover_page_is_a_notice_not_a_review_item(tmp_path) -> None:
    artifact = ingest_epub(
        _cover_epub(tmp_path, cover_page=SVG_COVER),
        edition_slug="cover-test-de-orig",
        work_slug="cover-test",
    )

    assert [(w.code, w.source_ref) for w in artifact.warnings] == [
        ("cover_document_skipped", "wrap0000.xhtml")
    ]
    assert ingestion_warning_severity("cover_document_skipped") == IngestionWarningSeverity.INFO
    # The cover is not content: the text still starts at the first chapter.
    assert [block.text for block in artifact.blocks] == ["Eins", "Der erste Abschnitt."]
    assert {block.chapter for block in artifact.blocks} == {0}


def test_an_svg_wrapped_illustration_becomes_an_image_block(tmp_path) -> None:
    plate = epub.EpubHtml(title="Plate", file_name="plate.xhtml", lang="de")
    plate.content = (
        '<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink">'
        '<image width="425" height="672" xlink:href="images/plate.jpg"/></svg>'
    )

    artifact = ingest_epub(
        _cover_epub(tmp_path, cover_page=SVG_COVER, extra=(plate,)),
        edition_slug="plate-test-de-orig",
        work_slug="plate-test",
    )

    image = artifact.blocks[0]
    assert image.type == BlockType.IMAGE
    assert image.source_ref == "images/plate.jpg"
    assert image.attributes == {"width": "425", "height": "672"}
    assert [w.code for w in artifact.warnings] == ["cover_document_skipped"]


def test_an_unexplained_empty_document_still_needs_review(tmp_path) -> None:
    blank = epub.EpubHtml(title="Blank", file_name="blank.xhtml", lang="de")
    blank.content = '<div class="ornament"></div>'

    artifact = ingest_epub(
        _cover_epub(tmp_path, cover_page=SVG_COVER, extra=(blank,)),
        edition_slug="blank-test-de-orig",
        work_slug="blank-test",
    )

    assert ("empty_spine_document", "blank.xhtml") in [
        (w.code, w.source_ref) for w in artifact.warnings
    ]
    assert ingestion_warning_severity("empty_spine_document") == IngestionWarningSeverity.WARNING


def test_inline_drop_cap_does_not_create_a_space():
    from almonium_book_processor.ingest.common import normalize_text, parse_html

    for markup, expected in [
        ('<p><span class="dropcap">I</span>t was dark.</p>', "It was dark."),
        ('<p><span class="dropcap">W</span>e returned.</p>', "We returned."),
        ('<p><span class="dropcap">C</span>lerval spoke.</p>', "Clerval spoke."),
        ('<p><span class="dropcap">I</span> am here.</p>', "I am here."),
    ]:
        assert normalize_text(parse_html(markup).p) == expected


def _gutenberg_epub(tmp_path, *, header: str, closing: str, licence_document: bool = True) -> str:
    """The shape Project Gutenberg ships: cover wrapper, header, chapters, footer."""

    source = tmp_path / "gutenberg.epub"
    book = epub.EpubBook()
    book.set_identifier("urn:test:gutenberg")
    book.set_title("Gutenberg Test")
    book.set_language("fr")
    book.add_author("Jules Verne")
    book.set_cover("cover.jpg", b"binary", create_page=False)

    wrapper = epub.EpubHtml(title="Cover", file_name="wrap0000.xhtml", lang="fr")
    wrapper.content = SVG_COVER
    first = epub.EpubHtml(title="First", file_name="800-0.xhtml", lang="fr")
    first.content = header + "<p>Jules Verne</p><h2>LE TOUR DU MONDE</h2><p>Premier chapitre.</p>"
    middle = epub.EpubHtml(title="Middle", file_name="800-1.xhtml", lang="fr")
    middle.content = "<h2>II</h2><p>Deuxième chapitre.</p>"
    last = epub.EpubHtml(title="Last", file_name="800-7.xhtml", lang="fr")
    last.content = "<p>Le Tour du Monde?</p><h5>FIN</h5>" + closing
    documents = [wrapper, first, middle, last]
    if licence_document:
        licence = epub.EpubHtml(title="Licence", file_name="800-8.xhtml", lang="en")
        licence.content = "<p>Section 1. General Terms of Use of Project Gutenberg-tm works</p>"
        documents.append(licence)
    for item in documents:
        book.add_item(item)
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    book.spine = ["nav", *documents]
    epub.write_epub(source, book)
    return str(source)


MODERN_HEADER = (
    '<div class="pg-boilerplate pgheader" id="pg-header"><h2>The Project Gutenberg eBook of '
    "<span>Le tour du monde</span></h2><div>This eBook is for the use of anyone anywhere.</div>"
    '<div id="pg-machine-header"><p><strong>Title</strong>: Le tour du monde</p></div>'
    '<div id="pg-start-separator"><span>*** START OF THE PROJECT GUTENBERG EBOOK '
    "LE TOUR DU MONDE ***</span></div></div>"
)
MODERN_FOOTER = (
    "<p>End of Project Gutenberg's Le Tour du Monde, by Jules Verne</p>"
    '<div class="pg-boilerplate pgheader footer" id="pg-footer"><div id="pg-end-separator">'
    "<span>*** END OF THE PROJECT GUTENBERG EBOOK LE TOUR DU MONDE ***</span></div>"
    "<div>Updated editions will replace the previous one.</div></div>"
)


def test_gutenberg_header_and_licence_are_cut_at_the_markers(tmp_path) -> None:
    artifact = ingest_epub(
        _gutenberg_epub(tmp_path, header=MODERN_HEADER, closing=MODERN_FOOTER),
        edition_slug="gutenberg-test-fr-orig",
        work_slug="gutenberg-test",
    )

    assert [block.text for block in artifact.blocks] == [
        "Jules Verne",
        "LE TOUR DU MONDE",
        "Premier chapitre.",
        "II",
        "Deuxième chapitre.",
        "Le Tour du Monde?",
        "FIN",
    ]
    assert [block.chapter for block in artifact.blocks] == [0, 0, 0, 1, 1, 2, 2]
    # Two notices, no review items: the cut is deliberate and the emptied
    # marker wrappers are not reported as skipped elements.
    assert [(w.code, w.source_ref) for w in artifact.warnings] == [
        ("gutenberg_boilerplate_trimmed", "800-0.xhtml"),
        ("gutenberg_boilerplate_trimmed", "800-7.xhtml"),
    ]
    assert "1 document(s) ahead" in artifact.warnings[0].message
    assert "1 document(s) after" in artifact.warnings[1].message
    assert (
        ingestion_warning_severity("gutenberg_boilerplate_trimmed") == IngestionWarningSeverity.INFO
    )


def test_an_old_gutenberg_header_shares_its_pre_with_the_marker(tmp_path) -> None:
    header = (
        "<pre>The Project Gutenberg EBook of Le Tour du Monde, by Jules Verne\n\n"
        "Title: Le Tour du Monde\n\n"
        "*** START OF THIS PROJECT GUTENBERG EBOOK LE TOUR DU MONDE ***\n\n\n\n"
        "Produced by ebooksgratuits\n</pre>"
    )
    closing = (
        "<pre>\nEnd of the Project Gutenberg EBook of Le Tour du Monde, by Jules Verne\n\n"
        "*** END OF THIS PROJECT GUTENBERG EBOOK LE TOUR DU MONDE ***\n\n"
        "***** This file should be named 800-8.txt *****\n</pre>"
    )

    artifact = ingest_epub(
        _gutenberg_epub(tmp_path, header=header, closing=closing, licence_document=False),
        edition_slug="gutenberg-old-fr-orig",
        work_slug="gutenberg-old",
    )

    texts = [block.text for block in artifact.blocks]
    assert texts[:2] == ["Produced by ebooksgratuits", "Jules Verne"]
    assert texts[-2:] == ["Le Tour du Monde?", "FIN"]
    assert not any("gutenberg" in text.lower() for text in texts)


def test_a_book_without_gutenberg_markers_is_left_alone(tmp_path) -> None:
    artifact = ingest_epub(
        _gutenberg_epub(tmp_path, header="<p>Preface.</p>", closing="<p>Colophon.</p>"),
        edition_slug="plain-fr-orig",
        work_slug="plain",
    )

    texts = [block.text for block in artifact.blocks]
    assert texts[0] == "Preface."
    assert texts[-1] == "Section 1. General Terms of Use of Project Gutenberg-tm works"
    assert [w.code for w in artifact.warnings] == ["cover_document_skipped"]


def _wikisource_epub(tmp_path, *, chapters: list[str], producer: bool = True) -> str:
    """The shape ws-export ships: its title page, the wiki's pages, its credits."""

    source = tmp_path / "wikisource.epub"
    book = epub.EpubBook()
    book.set_identifier("https://fr.wikisource.org/wiki/Le_Tour_du_monde")
    book.set_title("Le Tour du monde")
    book.set_language("fr")
    book.add_author("Jules Verne")
    if producer:
        book.add_metadata("DC", "contributor", "Wikisource")

    title = epub.EpubHtml(title="Title", file_name="title.xhtml", lang="fr")
    title.content = (
        "<h2>Le Tour du monde</h2><h3>Jules Verne</h3>"
        '<img alt="Wikisource logo" src="images/Wikisource-logo.svg.png"/>'
        "<h6>Exporté de Wikisource le 7 octobre 2026</h6>"
    )
    pages = []
    for index, content in enumerate(chapters):
        page = epub.EpubHtml(title=f"c{index}", file_name=f"c{index}_Le_Tour.xhtml", lang="fr")
        page.content = content
        pages.append(page)
    about = epub.EpubHtml(title="About", file_name="about.xhtml", lang="fr")
    about.content = (
        "<h1>À propos de cette édition électronique</h1>"
        "<p>Ce livre électronique est issu de la bibliothèque numérique Wikisource.</p>"
        "<p>Les contributeurs suivants ont permis la réalisation de ce livre :</p>"
        "<ul><li>Hsarrazin</li><li>Zyephyrus</li></ul>"
    )
    documents = [title, *pages, about]
    for item in documents:
        book.add_item(item)
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    book.spine = ["nav", *documents]
    epub.write_epub(source, book)
    return str(source)


WIKISOURCE_LICENCE_BANNER = (
    '<div class="licenseContainer licenseBanner dynlayout-exempt"><p>This work is in the '
    "public domain in the United States because it was published before 1931.</p></div>"
)


def test_a_wikisource_export_loses_its_title_page_credits_and_licence_banner(tmp_path) -> None:
    artifact = ingest_epub(
        _wikisource_epub(
            tmp_path,
            chapters=[
                "<h2>Le Tour du monde</h2><p>Table des matières.</p>" + WIKISOURCE_LICENCE_BANNER,
                "<h2>I</h2><p>En l'année 1872, la maison portant le numéro 7.</p>",
            ],
        ),
        edition_slug="tour-fr-orig",
        work_slug="tour",
    )

    texts = [block.text for block in artifact.blocks]
    assert texts == [
        "Le Tour du monde",
        "Table des matières.",
        "I",
        "En l'année 1872, la maison portant le numéro 7.",
    ]
    assert [(w.code, w.source_ref) for w in artifact.warnings] == [
        ("wikisource_matter_trimmed", "title.xhtml"),
        ("wikisource_matter_trimmed", "c0_Le_Tour.xhtml"),
        ("wikisource_matter_trimmed", "about.xhtml"),
    ]
    assert ingestion_warning_severity("wikisource_matter_trimmed") == IngestionWarningSeverity.INFO


def test_an_epub_wikisource_did_not_make_keeps_pages_with_those_names(tmp_path) -> None:
    source = _wikisource_epub(tmp_path, chapters=["<p>Un texte.</p>"], producer=False)
    # Neither the producer nor a wiki identifier: someone else's title page.
    book = epub.read_epub(source)
    book.set_unique_metadata("DC", "identifier", "urn:test:other")
    epub.write_epub(source, book)

    artifact = ingest_epub(source, edition_slug="other-fr-orig", work_slug="other")

    assert artifact.blocks[0].text == "Le Tour du monde"
    assert not any(w.code == "wikisource_matter_trimmed" for w in artifact.warnings)


@pytest.mark.parametrize(
    "listing",
    [
        '<div class="ws-disambiguation"><i>Cette page répertorie les différents œuvres.</i></div>'
        "<ul><li>Le Corbeau et le Renard (La Fontaine)</li><li>(Ésope)</li></ul>",
        '<img src="images/c1_big.svg_40px_Disambig.svg.png"/>'
        "<p>Wikisource propose plusieurs éditions de Le Horla.</p>"
        "<ul><li>Le Horla (Ollendorff 1895)</li><li>Le Horla (Conard 1909)</li></ul>",
    ],
)
def test_a_wikisource_disambiguation_page_is_refused(tmp_path, listing) -> None:
    with pytest.raises(ValueError, match="disambiguation page"):
        ingest_epub(
            _wikisource_epub(tmp_path, chapters=[listing]),
            edition_slug="corbeau-fr-orig",
            work_slug="corbeau",
        )


def _one_document_epub(tmp_path, content: str, *, name: str = "book.xhtml") -> str:
    """An EPUB whose whole text sits in one spine document, as Gutenberg's do."""

    source = tmp_path / "one-document.epub"
    book = epub.EpubBook()
    book.set_identifier("urn:test:one-document")
    book.set_title("One Document")
    book.set_language("es")
    book.add_author("Ada Author")
    document = epub.EpubHtml(title="Text", file_name=name, lang="es")
    document.content = content
    book.add_item(document)
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    book.spine = ["nav", document]
    epub.write_epub(source, book)
    return str(source)


def _prose(words: int, seed: str = "palabra") -> str:
    return " ".join(f"{seed}{index}" for index in range(words)) + "."


def _chapters(artifact) -> dict[int, list]:
    chapters: dict[int, list] = {}
    for block in artifact.blocks:
        chapters.setdefault(block.chapter, []).append(block)
    return chapters


def test_a_document_with_three_h2_chapters_is_split_at_them(tmp_path) -> None:
    content = "<h1>Marianela</h1><p>Por Benito Pérez Galdós</p>" + "".join(
        f'<h2 id="c{number}">-{numeral}- Capítulo</h2><p>{_prose(300)}</p><p>{_prose(300)}</p>'
        for number, numeral in enumerate(("I", "II", "III"), start=1)
    )

    artifact = ingest_epub(
        _one_document_epub(tmp_path, content), edition_slug="h2-es-orig", work_slug="h2"
    )

    chapters = _chapters(artifact)
    assert [chapter[0].text for chapter in chapters.values()] == [
        "Marianela",
        "-I- Capítulo",
        "-II- Capítulo",
        "-III- Capítulo",
    ]
    # The heading is the chapter's title block and nothing else: no repeat as a paragraph.
    assert [block.type for block in chapters[1]] == [
        BlockType.HEADING,
        BlockType.PARAGRAPH,
        BlockType.PARAGRAPH,
    ]
    assert chapters[1][0].source_ref == "book.xhtml#c1"
    assert [block.block_id for block in chapters[2]] == ["c2.h1", "c2.p2", "c2.p3"]
    split = [w for w in artifact.warnings if w.code == "spine_document_split"]
    assert len(split) == 1
    assert split[0].source_ref == "book.xhtml"
    assert split[0].chapter == 0
    assert "into 4 chapters" in split[0].message
    assert ingestion_warning_severity("spine_document_split") == IngestionWarningSeverity.INFO


def test_paragraph_chapter_labels_split_and_title_the_chapters(tmp_path) -> None:
    content = (
        f"<p>{_prose(200, 'prefacio')}</p>"
        f"<p>CAPÍTULO I</p><p>{_prose(300)}</p>"
        f"<p>CAPÍTULO II</p><p>{_prose(300)}</p>"
        f"<p>Capítulo III. La vuelta</p><p>{_prose(300)}</p>"
    )

    artifact = ingest_epub(
        _one_document_epub(tmp_path, content), edition_slug="label-es-orig", work_slug="label"
    )

    chapters = _chapters(artifact)
    assert len(chapters) == 4
    # Untitled preface material before the first label is a chapter of its own.
    assert [block.type for block in chapters[0]] == [BlockType.PARAGRAPH]
    assert [chapters[n][0].text for n in (1, 2, 3)] == [
        "CAPÍTULO I",
        "CAPÍTULO II",
        "Capítulo III. La vuelta",
    ]
    assert all(chapters[n][0].type == BlockType.HEADING for n in (1, 2, 3))
    assert all(len(chapters[n]) == 2 for n in (1, 2, 3))


def test_a_short_document_with_one_heading_is_not_split(tmp_path) -> None:
    content = f"<p>{_prose(60, 'intro')}</p><h2>Eins</h2><p>{_prose(120)}</p>"

    artifact = ingest_epub(
        _one_document_epub(tmp_path, content), edition_slug="short-es-orig", work_slug="short"
    )

    assert {block.chapter for block in artifact.blocks} == {0}
    assert not any(w.code == "spine_document_split" for w in artifact.warnings)


def test_a_title_page_with_several_headings_is_not_split(tmp_path) -> None:
    content = (
        "<h3>OEUVRES</h3><h5>DE VOLTAIRE</h5><p class='center'>RUE JACOB</p>"
        "<h3>OEUVRES</h3><p class='center'>RUE DU BATTOIR</p>"
        "<h1>CANDIDE,</h1><h5>OU L'OPTIMISME</h5>"
    )

    artifact = ingest_epub(
        _one_document_epub(tmp_path, content), edition_slug="title-fr-orig", work_slug="title"
    )

    assert {block.chapter for block in artifact.blocks} == {0}


def test_verse_inside_a_chapter_stays_whole(tmp_path) -> None:
    poem = (
        '<div class="poem"><h3>Canción</h3>'
        + "".join(f"<p>verso {index}<br/>otro verso {index}</p>" for index in range(40))
        + "</div>"
    )
    content = (
        f"<h2>I</h2><p>{_prose(2000)}</p>{poem}<p>{_prose(2000)}</p>"
        f"<h2>II</h2><p>{_prose(2000)}</p>"
    )

    artifact = ingest_epub(
        _one_document_epub(tmp_path, content), edition_slug="verse-es-orig", work_slug="verse"
    )

    chapters = _chapters(artifact)
    assert [chapter[0].text for chapter in chapters.values()] == ["I", "II"]
    first = chapters[0]
    assert any(block.type == BlockType.VERSE_LINE for block in first)
    # The poem's own heading and every verse line sit inside chapter I, with prose on both sides.
    types = [block.type for block in first]
    assert types[0] == BlockType.HEADING and types[1] == BlockType.PARAGRAPH
    assert types[-1] == BlockType.PARAGRAPH


def test_a_lone_section_numeral_does_not_start_a_chapter(tmp_path) -> None:
    content = (
        f"<h2>L'IVROGNE</h2><p>{_prose(2500)}</p><p>II</p><p>{_prose(1500)}</p>"
        f"<h2>UNE VENDETTA</h2><p>{_prose(2500)}</p>"
    )

    artifact = ingest_epub(
        _one_document_epub(tmp_path, content), edition_slug="section-fr-orig", work_slug="section"
    )

    chapters = _chapters(artifact)
    assert [chapter[0].text for chapter in chapters.values()] == ["L'IVROGNE", "UNE VENDETTA"]
    assert "II" in [block.text for block in chapters[0]]


def test_a_file_cut_mid_chapter_continues_the_previous_chapter(tmp_path) -> None:
    source = tmp_path / "cut.epub"
    book = epub.EpubBook()
    book.set_identifier("urn:test:cut")
    book.set_title("Cut Test")
    book.set_language("fr")
    book.add_author("Ada Author")
    first = epub.EpubHtml(title="h-0", file_name="h-0.xhtml", lang="fr")
    first.content = f"<h2>LE PÈRE</h2><p>{_prose(2500)}</p><h2>LE VIEUX</h2><p>{_prose(2500)}</p>"
    second = epub.EpubHtml(title="h-1", file_name="h-1.xhtml", lang="fr")
    second.content = f"<p>{_prose(800, 'suite')}</p><h2>UN LÂCHE</h2><p>{_prose(2500)}</p>"
    for item in (first, second, epub.EpubNcx(), epub.EpubNav()):
        book.add_item(item)
    book.spine = ["nav", first, second]
    epub.write_epub(source, book)

    artifact = ingest_epub(source, edition_slug="cut-fr-orig", work_slug="cut")

    chapters = _chapters(artifact)
    assert [chapter[0].text for chapter in chapters.values()] == ["LE PÈRE", "LE VIEUX", "UN LÂCHE"]
    assert chapters[1][-1].text.startswith("suite0 ")
    assert chapters[1][-1].source_ref == "h-1.xhtml"


def test_a_long_document_without_headings_is_cut_by_size(tmp_path) -> None:
    # Damiano: 766,000 characters in two files with no chapter marks; Venus im Pelz: 241,000 in one
    content = "".join(f"<p>{_prose(1200)}</p>" for _ in range(8))
    artifact = ingest_epub(
        _one_document_epub(tmp_path, content), edition_slug="long-es-orig", work_slug="long"
    )
    chapters = _chapters(artifact)
    sizes = [sum(len(block.text) for block in blocks) for blocks in chapters.values()]
    assert len(chapters) >= 3
    # a cut falls between paragraphs: no paragraph is torn and every part is near the target
    assert all(block.type == BlockType.PARAGRAPH for block in artifact.blocks)
    assert max(sizes) < 20_000 + max(len(block.text) for block in artifact.blocks)
    assert sum(sizes) == sum(len(block.text) for block in artifact.blocks)
    cut = [w for w in artifact.warnings if w.code == "long_document_split_by_size"]
    assert len(cut) == 1 and cut[0].source_ref == "book.xhtml"
    assert (
        ingestion_warning_severity("long_document_split_by_size") == IngestionWarningSeverity.INFO
    )
    assert not any(w.code == "long_document_unsplit" for w in artifact.warnings)


@pytest.mark.skipif(
    not os.environ.get("ALMONIUM_TEST_GUTENBERG_EPUB"),
    reason="set ALMONIUM_TEST_GUTENBERG_EPUB to a downloaded Gutenberg EPUB",
)
def test_a_real_gutenberg_epub_yields_readable_chapters() -> None:
    """Runs only against a file already on disk; CI never downloads a book.

    ALMONIUM_TEST_GUTENBERG_MIN_CHAPTERS and ALMONIUM_TEST_GUTENBERG_MAX_CHAPTER_CHARS
    tune the expectation for the book at hand (defaults: 3 chapters, 60,000 characters).
    """

    path = os.environ["ALMONIUM_TEST_GUTENBERG_EPUB"]
    min_chapters = int(os.environ.get("ALMONIUM_TEST_GUTENBERG_MIN_CHAPTERS", "3"))
    max_chars = int(os.environ.get("ALMONIUM_TEST_GUTENBERG_MAX_CHAPTER_CHARS", "60000"))

    artifact = ingest_epub(path, edition_slug="real-orig", work_slug="real")

    chapters = _chapters(artifact)
    assert len(chapters) >= min_chapters
    sizes = {
        number: sum(len(block.text) for block in blocks) for number, blocks in chapters.items()
    }
    assert max(sizes.values()) <= max_chars, sizes
    assert not any(w.code == "long_document_unsplit" for w in artifact.warnings)


def test_chapters_marked_with_h4_and_titled_with_h5_are_split_at_the_h4(tmp_path) -> None:
    # Gutenberg's Dom Casmurro (55752) and O Cortiço (69187): a title page of h4/h5 lines, then
    # every chapter an h4 label with its title in an h5. They came in as one 65,000-word chapter.
    title_page = (
        "<h4>DOM CASMURRO</h4><h5>B. L. GARNIER, LIVREIRO-EDITOR</h5>"
        "<h5>RIO DE JANEIRO</h5><h5>1899</h5>"
    )
    content = title_page + "".join(
        f'<h4 id="c{number}">CAPÍTULO {numeral}</h4><h5>{title}</h5>'
        f"<p>{_prose(300)}</p><p>{_prose(300)}</p>"
        for number, (numeral, title) in enumerate(
            (("I", "Do titulo"), ("II", "Do livro"), ("III", "A denuncia")), start=1
        )
    )

    artifact = ingest_epub(
        _one_document_epub(tmp_path, content), edition_slug="h4-pt-orig", work_slug="h4"
    )

    chapters = _chapters(artifact)
    # the title page's headings run straight into the first chapter's, so they are one chapter
    assert [chapter[0].text for chapter in chapters.values()] == [
        "DOM CASMURRO",
        "CAPÍTULO II",
        "CAPÍTULO III",
    ]
    assert "CAPÍTULO I" in [block.text for block in chapters[0]]
    # the h5 title stays inside its chapter as a heading block, not a chapter of its own
    assert [block.type for block in chapters[1]][:2] == [BlockType.HEADING, BlockType.HEADING]
    assert chapters[1][1].text == "Do livro"


def _book(tmp_path, documents, *, author="Ada Author"):
    source = tmp_path / "book.epub"
    book = epub.EpubBook()
    book.set_identifier("urn:test:fold")
    book.set_title("Also sprach Zarathustra")
    book.set_language("de")
    if author:
        book.add_author(author)
    items = []
    for index, content in enumerate(documents):
        item = epub.EpubHtml(title=f"d{index}", file_name=f"text/d{index}.xhtml", lang="de")
        item.content = content
        book.add_item(item)
        items.append(item)
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    book.spine = ["nav", *items]
    epub.write_epub(source, book)
    return source


def test_a_heading_only_chapter_joins_the_next_as_its_part_label(tmp_path) -> None:
    # Zarathustra: the book's title and "Erster Theil" each stood as a chapter of their heading
    source = _book(
        tmp_path,
        [
            "<h1>Also sprach Zarathustra</h1>",
            "<h2>Erster Theil</h2>",
            "<h2>Zarathustra's Vorrede</h2><p>Als Zarathustra dreissig Jahr alt war.</p>",
            "<h2>Die Reden Zarathustra's</h2><p>Drei Verwandlungen nenne ich euch.</p>",
        ],
    )

    artifact = ingest_epub(source, edition_slug="z-de", work_slug="z")

    assert [block.chapter for block in artifact.blocks] == [0, 0, 0, 0, 1, 1]
    assert [block.text for block in artifact.blocks[:4]] == [
        "Also sprach Zarathustra",
        "Erster Theil",
        "Zarathustra's Vorrede",
        "Als Zarathustra dreissig Jahr alt war.",
    ]
    # the joined headings are part labels; the chapter's own title is the third heading
    assert [block.attributes.get("part") for block in artifact.blocks[:3]] == [True, True, None]
    assert [block.block_id for block in artifact.blocks] == [
        "c0.h1",
        "c0.h2",
        "c0.h3",
        "c0.p4",
        "c1.h1",
        "c1.p2",
    ]
    assert "heading_only_chapters_folded" in [w.code for w in artifact.warnings]


def test_a_book_without_an_author_is_still_a_book(tmp_path) -> None:
    source = _book(tmp_path, ["<h2>I</h2><p>Anonymous words.</p>"], author=None)

    artifact = ingest_epub(source, edition_slug="a-de", work_slug="a")

    assert artifact.edition.author == "Unknown"
    assert "author_missing" in [w.code for w in artifact.warnings]


def test_a_long_chapter_after_a_heading_and_a_continuing_file_are_cut_by_size(tmp_path) -> None:
    # Venus im Pelz: one heading, then 116,000 characters; the next file of 88,000 opens in
    # prose and continued the chapter. Both come out in parts of about 20,000.
    source = tmp_path / "book.epub"
    book = epub.EpubBook()
    book.set_identifier("urn:test:venus")
    book.set_title("Venus im Pelz")
    book.set_language("de")
    book.add_author("Leopold von Sacher-Masoch")
    first = epub.EpubHtml(title="a", file_name="text/a.xhtml", lang="de")
    first.content = "<h2>Venus im Pelz</h2>" + "".join(f"<p>{_prose(1200)}</p>" for _ in range(8))
    second = epub.EpubHtml(title="b", file_name="text/b.xhtml", lang="de")
    second.content = "".join(f"<p>{_prose(1200)}</p>" for _ in range(6))
    for item in (first, second, epub.EpubNcx(), epub.EpubNav()):
        book.add_item(item)
    book.spine = ["nav", first, second]
    epub.write_epub(source, book)

    artifact = ingest_epub(source, edition_slug="venus-de", work_slug="venus")

    chapters = _chapters(artifact)
    sizes = [sum(len(block.text) for block in blocks) for blocks in chapters.values()]
    longest_paragraph = max(len(block.text) for block in artifact.blocks)
    assert len(chapters) >= 5
    assert max(sizes) < 20_000 + longest_paragraph
    assert (
        artifact.blocks[0].text == "Venus im Pelz" and artifact.blocks[0].type == BlockType.HEADING
    )
    assert sum(1 for w in artifact.warnings if w.code == "long_document_split_by_size") == 2
    # every part carries the mark that makes it the story for the chapter roles
    assert all(block.attributes.get("cut") == "size" for block in artifact.blocks)


def test_a_closing_word_ends_the_last_chapter_instead_of_opening_one(tmp_path) -> None:
    # Damiano closes with a page that says only "FINE."
    source = _book(
        tmp_path,
        [
            "<h2>I</h2><p>Primo capitolo della storia.</p>",
            "<h2>II</h2><p>Secondo capitolo della storia.</p>",
            "<h2>FINE.</h2>",
        ],
    )

    artifact = ingest_epub(source, edition_slug="d-it", work_slug="d")

    assert [block.chapter for block in artifact.blocks] == [0, 0, 1, 1, 1]
    assert artifact.blocks[-1].text == "FINE." and artifact.blocks[-1].attributes.get("part")


def test_wolne_lektury_pages_are_dropped_and_the_footnotes_stay(tmp_path) -> None:
    # wolnelektury.pl: the text in one file, fundraising pages between the chapters
    source = tmp_path / "wolne.epub"
    book = epub.EpubBook()
    book.set_identifier("http://wolnelektury.pl/katalog/lektura/balzac-gabinet-starozytnosci")
    book.set_title("Gabinet Starożytności")
    book.set_language("pl")
    book.add_author("Honoré de Balzac")
    book.add_metadata("DC", "publisher", "Fundacja Wolne Lektury")
    pages = {
        "title.xhtml": "<h2>Strona tytułowa</h2><p>Ta lektura jest dostępna on-line.</p>",
        "fund0.xhtml": "<p>Książka, którą czytasz, pochodzi z biblioteki Wolne Lektury.</p>",
        "part1.xhtml": "<h2>Gabinet Starożytności</h2>",
        "part2.xhtml": "<h2>Rozdział I</h2><p>Pierwszy.</p><h2>Rozdział II</h2><p>Drugi.</p>",
        "fund1.xhtml": "<p>Wesprzyj naszą zbiórkę!</p>",
        "annotations.xhtml": "<h2>Przypisy:</h2><p>1. Objaśnienie.</p>",
        "support.xhtml": "<h2>Wesprzyj Wolne Lektury!</h2><p>Co roku...</p>",
        "last.xhtml": "<h2>Strona redakcyjna</h2><p>Licencja.</p>",
    }
    items = []
    for name, content in pages.items():
        item = epub.EpubHtml(title=name, file_name=f"EPUB/{name}", lang="pl")
        item.content = content
        book.add_item(item)
        items.append(item)
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    book.spine = ["nav", *items]
    epub.write_epub(source, book)

    artifact = ingest_epub(source, edition_slug="gabinet-pl", work_slug="gabinet")

    texts = [block.text for block in artifact.blocks]
    assert "Wesprzyj naszą zbiórkę!" not in texts and "Licencja." not in texts
    assert "Ta lektura jest dostępna on-line." not in texts
    assert texts == [
        "Gabinet Starożytności",
        "Rozdział I",
        "Pierwszy.",
        "Rozdział II",
        "Drugi.",
        "Przypisy:",
        "1. Objaśnienie.",
    ]
    assert artifact.blocks[0].attributes.get("part") is True  # the bare title page is a label
    assert "wolne_lektury_matter_trimmed" in [w.code for w in artifact.warnings]


def test_verse_set_with_line_breaks_and_no_paragraphs_is_read_as_stanzas(tmp_path) -> None:
    # Os Lusíadas on Gutenberg: a <div> with 2,656 <br> and not one <p>; it came in as 300 chars
    source = _book(
        tmp_path,
        [
            "<div><h3>Canto Sétimo</h3><br/> 1<br/> Já se viam chegados junto à terra,<br/>"
            " Que desejada já de tantos fora,<br/> Que entre as correntes Indicas se encerra,<br/>"
            "<br/> 2<br/> A vós, ó geração de Luso, digo,<br/> Que tão pequena parte sois no mundo;"
            "<br/> Não digo ainda no mundo, mas no amigo<br/></div>"
        ],
    )

    artifact = ingest_epub(source, edition_slug="lus-pt", work_slug="lus")

    assert [block.type for block in artifact.blocks] == [
        BlockType.HEADING,
        BlockType.VERSE_STANZA,
        BlockType.VERSE_STANZA,
    ]
    assert artifact.blocks[1].text.split("\n") == [
        "1",
        "Já se viam chegados junto à terra,",
        "Que desejada já de tantos fora,",
        "Que entre as correntes Indicas se encerra,",
    ]


def test_plain_text_born_prose_with_blank_lines_is_read_as_paragraphs(tmp_path) -> None:
    long = "Toto je dlouhý řádek prózy, který se láme na konci řádku jako v textovém souboru. "
    source = _book(
        tmp_path,
        [f"<div><h2>I</h2>\n{long}\n{long}\n\n{long}\n{long}\n</div>"],
    )

    artifact = ingest_epub(source, edition_slug="rur-cs", work_slug="rur")

    assert [block.type for block in artifact.blocks] == [
        BlockType.HEADING,
        BlockType.PARAGRAPH,
        BlockType.PARAGRAPH,
    ]
    assert artifact.blocks[1].text == f"{long.strip()} {long.strip()}"


def test_a_play_is_not_cut_at_every_speaker(tmp_path) -> None:
    # Palvelusväkeä: 307 chapters called PEKKA and HANNA
    speeches = "".join(f"<h3>{name}</h3><p>{_prose(40)}</p>" for name in ["PEKKA", "HANNA"] * 40)
    source = _book(
        tmp_path, [f"<h2>ENSIMMÄINEN NÄYTÖS</h2>{speeches}<h2>TOINEN NÄYTÖS</h2>{speeches}"]
    )

    artifact = ingest_epub(source, edition_slug="play-fi", work_slug="play")

    assert len({block.chapter for block in artifact.blocks}) == 2


def test_a_book_laid_out_in_one_table_is_still_cut_at_its_headings(tmp_path) -> None:
    # R.U.R. on Gutenberg: the whole play inside a centred table
    acts = "".join(
        f"<h2>{name}</h2>" + "".join(f"<p>{_prose(60)}</p>" for _ in range(30))
        for name in ("PŘEDEHRA", "DĚJSTVÍ PRVNÍ", "DĚJSTVÍ DRUHÉ")
    )
    source = _book(tmp_path, [f"<div><table><tbody><tr><td>{acts}</td></tr></tbody></table></div>"])

    artifact = ingest_epub(source, edition_slug="rur-cs", work_slug="rur")

    chapters = _chapters(artifact)
    assert [blocks[0].text for blocks in chapters.values()] == [
        "PŘEDEHRA",
        "DĚJSTVÍ PRVNÍ",
        "DĚJSTVÍ DRUHÉ",
    ]


def test_loose_verse_of_a_whole_book_is_cut_by_size_between_stanzas(tmp_path) -> None:
    # the Greek Iliad: 630,000 characters of verse parted by <br>, no paragraphs, two headings
    stanza = "<br/>".join(
        f"Line {n} of the song of wrath and of the shining helmets" for n in range(8)
    )
    text = "<br/><br/>".join(stanza for _ in range(260))  # about 130,000 characters
    source = _book(tmp_path, [f"<div><h2>ΡΑΨΩΔΙΑ Α</h2><br/>{text}</div>"])

    artifact = ingest_epub(source, edition_slug="iliad-el", work_slug="iliad")

    chapters = _chapters(artifact)
    sizes = [sum(len(block.text) for block in blocks) for blocks in chapters.values()]
    assert len(chapters) >= 5 and max(sizes) < 25_000
    assert all(
        block.type in (BlockType.HEADING, BlockType.VERSE_STANZA) for block in artifact.blocks
    )
    # no stanza was torn: every stanza block still has its eight lines
    assert all(
        block.attributes.get("line_count") == 8
        for block in artifact.blocks
        if block.type == BlockType.VERSE_STANZA
    )


def test_a_poem_laid_out_as_a_numbered_table_is_read_line_by_line_and_cut_by_size(tmp_path) -> None:
    # the Greek Iliad on Gutenberg: a title page, then one table of 13,989 rows, a number and a line
    verse = "of the song of wrath and shining helms"
    rows = "".join(
        f"<tr><td>{n if n % 5 == 0 else ''}</td><td>Line {n} {verse}</td></tr>"
        for n in range(1, 2001)
    )
    source = _book(tmp_path, [f"<h1>ΙΛΙΑΔΑ</h1><p>ΤΟΥ</p><table><tbody>{rows}</tbody></table>"])

    artifact = ingest_epub(source, edition_slug="iliad-el", work_slug="iliad")

    lines = [block for block in artifact.blocks if block.type == BlockType.VERSE_LINE]
    assert len(lines) == 2000
    assert lines[4].text == f"Line 5 {verse}"  # the number is dropped
    chapters = _chapters(artifact)
    assert len(chapters) >= 4
    assert max(sum(len(block.text) for block in blocks) for blocks in chapters.values()) < 25_000


def test_an_edition_records_the_cut_that_made_it(tmp_path) -> None:
    from almonium_book_processor.ingest.common import INGEST_VERSION

    source = _book(tmp_path, ["<h2>I</h2><p>Words.</p>"])
    artifact = ingest_epub(source, edition_slug="cut-de", work_slug="cut")
    assert artifact.processor_version.endswith(f"+{INGEST_VERSION}")
