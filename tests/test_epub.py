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
