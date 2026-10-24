"""Cut Wolne Lektury's own pages out of an EPUB before extraction.

The Polish library (wolnelektury.pl, Fundacja Wolne Lektury) exports the text as one document
with the chapters at its headings, and around it its own pages: a title page that also asks for
support, fundraising pages between the chapters (``fund0.xhtml`` …), a support page, and an
editorial page with the licence. None of it is the book. The footnotes (``annotations.xhtml``,
"Przypisy") are the book's and stay, as back matter.
"""

from __future__ import annotations

import re
from pathlib import PurePosixPath
from urllib.parse import urlsplit

from bs4 import Tag
from ebooklib import epub

from almonium_book_processor.models import IngestionWarning

Document = tuple[str, Tag]
LIBRARY_PAGES = re.compile(r"^(fund\d*|support|last|title)\.x?html$")


def is_wolne_lektury(book: epub.EpubBook) -> bool:
    """True when the EPUB came from Wolne Lektury: it says so as publisher or identifier."""

    publishers = {str(value).casefold() for value, _ in book.get_metadata("DC", "publisher")}
    if any("wolne lektury" in publisher for publisher in publishers):
        return True
    for value, _ in book.get_metadata("DC", "identifier"):
        host = (urlsplit(str(value).strip()).hostname or "").casefold()
        if host == "wolnelektury.pl" or host.endswith(".wolnelektury.pl"):
            return True
    return False


def trim_wolne_lektury_matter(
    documents: list[Document],
) -> tuple[list[Document], list[IngestionWarning]]:
    """Drop the library's own pages; the text and its footnotes stay."""

    kept: list[Document] = []
    dropped: list[str] = []
    for name, root in documents:
        if LIBRARY_PAGES.match(PurePosixPath(name).name):
            dropped.append(PurePosixPath(name).name)
            continue
        kept.append((name, root))
    warnings = (
        [
            IngestionWarning(
                code="wolne_lektury_matter_trimmed",
                message=(
                    f"Dropped {len(dropped)} Wolne Lektury page(s): the title page, the "
                    "fundraising pages between the chapters, the support and editorial pages"
                ),
                source_ref=", ".join(dropped[:6]),
            )
        ]
        if dropped
        else []
    )
    return kept, warnings
