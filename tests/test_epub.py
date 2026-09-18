from __future__ import annotations

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
