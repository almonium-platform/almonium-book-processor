"""Cut Wikisource's export pages and licence banners out of a ws-export EPUB.

Wikisource's official exporter (ws-export.wmcloud.org) wraps the text in pages
of its own: ``title.xhtml``, a title page that ends "Exported from Wikisource on
<date>", and ``about.xhtml``, "About this digital edition", which carries the
CC BY-SA/GFDL notice and the list of every volunteer who touched the
transcription, often several screens long. The index page also ends with the
wiki's licence banner ("This work is in the public domain in the United
States..."). None of it is the book. The exporter names both pages the same
way in every language, and the banner is one ``licenseContainer`` element, so
they are dropped by name and class rather than by wording.

A page title that names several works, or several editions of one, exports
the list of them instead of a text; that is refused outright, because nothing
downstream can make a book of it. Such a page carries the wiki's disambiguation
class or Commons' "Disambig" icon and little else.
"""

from __future__ import annotations

from pathlib import PurePosixPath
from urllib.parse import urlsplit

from bs4 import Tag
from ebooklib import epub

from almonium_book_processor.models import IngestionWarning

EXPORT_PAGES = {"title.xhtml", "about.xhtml"}
LICENCE_BANNER_CLASS = "licenseContainer"
DISAMBIGUATION_CLASS = "ws-disambiguation"
DISAMBIGUATION_ICON = "disambig"
# A list of works or editions is a few lines; a text that merely opens with a
# "for other editions, see..." note runs far longer.
DISAMBIGUATION_MAX_CHARS = 3000

Document = tuple[str, Tag]


def is_wikisource_export(book: epub.EpubBook) -> bool:
    """True when the EPUB was made by Wikisource's exporter.

    The exporter names Wikisource as the book producer and the wiki page as
    the identifier and source; either is enough.
    """

    contributors = {
        str(value).strip().casefold() for value, _ in book.get_metadata("DC", "contributor")
    }
    if "wikisource" in contributors:
        return True
    for name in ("source", "identifier"):
        for value, _ in book.get_metadata("DC", name):
            host = (urlsplit(str(value).strip()).hostname or "").casefold()
            if host == "wikisource.org" or host.endswith(".wikisource.org"):
                return True
    return False


def trim_wikisource_matter(
    documents: list[Document],
) -> tuple[list[Document], list[IngestionWarning]]:
    """Drop the exporter's own pages and the licence banners from the rest."""

    warnings: list[IngestionWarning] = []
    kept: list[Document] = []
    for name, root in documents:
        if PurePosixPath(name).name in EXPORT_PAGES:
            warnings.append(
                IngestionWarning(
                    code="wikisource_matter_trimmed",
                    message="Dropped the Wikisource export page (title page or credits)",
                    source_ref=name,
                )
            )
            continue
        banners = root.find_all(class_=LICENCE_BANNER_CLASS)
        for banner in banners:
            banner.decompose()
        if banners:
            warnings.append(
                IngestionWarning(
                    code="wikisource_matter_trimmed",
                    message="Dropped the Wikisource licence banner",
                    source_ref=name,
                )
            )
        kept.append((name, root))
    if kept and all(_is_disambiguation(root) for _, root in kept):
        raise ValueError(
            "Wikisource exported a disambiguation page, not a text: the page title names "
            "several works or editions. Ask for the page of one edition instead."
        )
    return kept, warnings


def _is_disambiguation(root: Tag) -> bool:
    if root.find(class_=DISAMBIGUATION_CLASS) is not None:
        return True
    if len(root.get_text(" ", strip=True)) > DISAMBIGUATION_MAX_CHARS:
        return False
    return any(
        DISAMBIGUATION_ICON in f"{image.get('src', '')} {image.get('resource', '')}".casefold()
        for image in root.find_all("img")
    )
