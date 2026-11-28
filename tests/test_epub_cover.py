"""The cover a reader's own EPUB carries."""

from __future__ import annotations

import io
import zipfile

from almonium_book_processor.ingest.epub_cover import find_cover, has_cover

CONTAINER = (
    '<?xml version="1.0"?><container xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
    '<rootfiles><rootfile full-path="OEBPS/content.opf"/></rootfiles></container>'
)
BIG = b"\x89PNG" + b"0" * 20_000
SMALL = b"\x89PNG" + b"0" * 500


def epub(manifest: str, files: dict[str, bytes], meta: str = "") -> io.BytesIO:
    package = (
        '<package xmlns="http://www.idpf.org/2007/opf"><metadata>'
        f"{meta}</metadata><manifest>{manifest}</manifest></package>"
    )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("META-INF/container.xml", CONTAINER)
        archive.writestr("OEBPS/content.opf", package)
        for name, data in files.items():
            archive.writestr(f"OEBPS/{name}", data)
    buffer.seek(0)
    return buffer


def test_the_image_the_package_declares_as_its_cover_is_the_cover():
    book = epub(
        '<item id="p1" href="images/plate.png" media-type="image/png"/>'
        '<item id="c" href="images/front.jpg" media-type="image/jpeg" properties="cover-image"/>',
        {"images/plate.png": BIG, "images/front.jpg": b"the cover"},
    )

    assert find_cover(book) == (b"the cover", "image/jpeg")


def test_an_older_book_names_its_cover_in_the_metadata():
    book = epub(
        '<item id="p1" href="plate.png" media-type="image/png"/>'
        '<item id="jacket" href="jacket.png" media-type="image/png"/>',
        {"plate.png": BIG, "jacket.png": b"the jacket"},
        meta='<meta name="cover" content="jacket"/>',
    )

    assert find_cover(book) == (b"the jacket", "image/png")


def test_a_book_that_declares_none_gives_its_first_picture_of_any_size():
    book = epub(
        '<item id="logo" href="logo.png" media-type="image/png"/>'
        '<item id="p1" href="plate.png" media-type="image/png"/>'
        '<item id="text" href="chapter.xhtml" media-type="application/xhtml+xml"/>',
        {"logo.png": SMALL, "plate.png": BIG, "chapter.xhtml": b"<html/>"},
    )

    assert find_cover(book) == (BIG, "image/png")
    assert has_cover(book)


def test_a_book_without_pictures_and_a_file_that_is_no_epub_have_no_cover():
    plain = epub(
        '<item id="text" href="c.xhtml" media-type="application/xhtml+xml"/>', {"c.xhtml": b"x"}
    )

    assert find_cover(plain) is None and not has_cover(plain)
    assert find_cover(io.BytesIO(b"<TEI>not a zip</TEI>")) is None
    assert not has_cover(io.BytesIO(b""))
