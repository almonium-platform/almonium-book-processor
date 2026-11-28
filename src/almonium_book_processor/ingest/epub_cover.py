"""The cover a reader's own EPUB carries, read straight from the file.

Almonium draws a typographic cover for a book it knows nothing about. An upload usually
brings its own: the image the package declares as its cover, or failing that the first
picture of any size in the book. Nothing is unpacked or kept; the file is asked each time,
which is a zip directory and one small XML document.
"""

from __future__ import annotations

import posixpath
import zipfile
from typing import IO
from xml.etree import ElementTree

CONTAINER = "META-INF/container.xml"
IMAGE_TYPES = {"image/jpeg": ".jpg", "image/png": ".png"}
# smaller than this is an ornament or a publisher's mark, not a picture worth a cover
MIN_BYTES = 8_000
MAX_BYTES = 6_000_000


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _manifest(archive: zipfile.ZipFile) -> tuple[list[dict[str, str]], str | None, str]:
    """The package's manifest items, the id its metadata names as the cover, and its folder."""

    container = ElementTree.fromstring(archive.read(CONTAINER))  # noqa: S314 - the owner's file
    rootfile = next(
        element.get("full-path", "")
        for element in container.iter()
        if _local(element.tag) == "rootfile"
    )
    package = ElementTree.fromstring(archive.read(rootfile))  # noqa: S314
    items = [dict(element.attrib) for element in package.iter() if _local(element.tag) == "item"]
    named = next(
        (
            element.get("content")
            for element in package.iter()
            if _local(element.tag) == "meta" and element.get("name") == "cover"
        ),
        None,
    )
    return items, named, posixpath.dirname(rootfile)


def _cover_item(archive: zipfile.ZipFile) -> tuple[str, str] | None:
    """The archive path and media type of the image to use, or None when the book has none."""

    items, named, folder = _manifest(archive)
    images = [item for item in items if item.get("media-type") in IMAGE_TYPES]
    sizes = {info.filename: info.file_size for info in archive.infolist()}

    def path(item: dict[str, str]) -> str:
        return posixpath.normpath(posixpath.join(folder, item.get("href", "")))

    def usable(item: dict[str, str], *, least: int = 1) -> bool:
        return least <= sizes.get(path(item), 0) <= MAX_BYTES

    declared = [item for item in images if "cover-image" in item.get("properties", "").split()]
    declared += [item for item in images if named and item.get("id") == named]
    declared += [
        item
        for item in images
        if "cover" in (item.get("id", "") + posixpath.basename(item.get("href", ""))).lower()
    ]
    chosen = next((item for item in declared if usable(item)), None) or next(
        (item for item in images if usable(item, least=MIN_BYTES)), None
    )
    return (path(chosen), chosen["media-type"]) if chosen else None


def find_cover(source: IO[bytes]) -> tuple[bytes, str] | None:
    """The cover image of an EPUB and its media type; None for a book without one, a file
    that is not an EPUB, or one too damaged to read."""

    try:
        with zipfile.ZipFile(source) as archive:
            found = _cover_item(archive)
            return (archive.read(found[0]), found[1]) if found else None
    except (zipfile.BadZipFile, KeyError, StopIteration, ElementTree.ParseError, OSError):
        return None


def has_cover(source: IO[bytes]) -> bool:
    try:
        with zipfile.ZipFile(source) as archive:
            return _cover_item(archive) is not None
    except (zipfile.BadZipFile, KeyError, StopIteration, ElementTree.ParseError, OSError):
        return False
