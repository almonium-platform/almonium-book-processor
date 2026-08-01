from __future__ import annotations

from ebooklib import epub

from almonium_book_processor.ingest.epub import ingest_epub
from almonium_book_processor.models import BlockType


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
        edition_id="spine-test-de-orig",
        work_id="spine-test",
    )

    assert artifact.edition.title == "Spine Test"
    assert artifact.edition.source.identifier == "urn:test:book"
    assert [block.text for block in artifact.blocks[:2]] == ["Eins", "Der erste Abschnitt."]
    assert artifact.blocks[2].type == BlockType.IMAGE
    assert artifact.blocks[2].source_ref == "images/plate.jpg"
    assert [block.text for block in artifact.blocks[3:]] == ["Zwei", "Der zweite Abschnitt."]
    assert [block.chapter for block in artifact.blocks] == [0, 0, 0, 1, 1]
