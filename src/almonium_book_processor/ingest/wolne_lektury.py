"""Cut what is Wolne Lektury's own out of an EPUB before extraction.

The Polish library (wolnelektury.pl, Fundacja Wolne Lektury) exports the text as one document
with the chapters at its headings, and around it its own pages: a title page that also asks for
support, fundraising pages between the chapters (``fund0.xhtml`` …), a support page, and an
editorial page with the licence. None of it is the book.

Nor are the library's notes. The author's text is in the public domain; the notes the library's
editors wrote ("[przypis edytorski]", 349 of them on Sklepy cynamonowe) are theirs, under the
Licencja Wolnej Sztuki, and their numbers stand in the text glued to the words: "Pomona1 z ognia
dnia rozżagwionego2". Only the author's own notes ("[przypis autorski]") stay, with their
numbers; every other note goes, and its number with it.

A collection is exported with each work's title on a page of its own and each numbered section
of a work on the next pages, every one of them a chapter to the splitter: Sierpień came in as
chapters "1", "2" and "3". In a collection a work is one chapter under its own title.
"""

from __future__ import annotations

import re
from pathlib import PurePosixPath
from urllib.parse import urlsplit

from bs4 import NavigableString, Tag
from ebooklib import epub

from almonium_book_processor.ingest.common import HEADING_TAGS, normalize_text
from almonium_book_processor.models import IngestionWarning

Document = tuple[str, Tag]
LIBRARY_PAGES = re.compile(r"^(fund\d*|support|last|title)\.x?html$")
NOTES_PAGE = "annotations.xhtml"
TEXT_PAGE = re.compile(r"^part\d+\.x?html$")
AUTHORS_NOTE = "[przypis autorski]"
# librarian's EPUB stylesheet: a work's title inside a collection, and the line under it
WORK_TITLE = "intitle"
WORK_SUBTITLE = "insubtitle"
# the one heading the chapter splitter never cuts at: a section inside its chapter
SECTION_TAG = "h6"


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
    """Drop the library's pages and notes; keep each work of a collection in one piece."""

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
    kept, notes = _drop_library_notes(kept)
    if notes:
        warnings.append(
            IngestionWarning(
                code="wolne_lektury_notes_dropped",
                message=(
                    f"Dropped {notes} note(s) written by the library's editors and their "
                    "numbers in the text; the author's own notes stay"
                ),
                source_ref=NOTES_PAGE,
            )
        )
    kept, joined = _join_works(kept)
    if joined:
        warnings.append(
            IngestionWarning(
                code="wolne_lektury_works_joined",
                message=(
                    f"Joined {joined} page(s) of numbered sections to the works they belong "
                    "to: in a collection each work is one chapter under its own title"
                ),
            )
        )
    return kept, warnings


def _drop_library_notes(documents: list[Document]) -> tuple[list[Document], int]:
    """Take out every note the author did not write, and the number that points at it."""

    page = next((d for d in documents if PurePosixPath(d[0]).name == NOTES_PAGE), None)
    if page is None:
        return documents, 0
    gone: set[str] = set()
    for note in page[1].find_all(class_="annotation"):
        if AUTHORS_NOTE in note.get_text():
            continue
        if note.get("id"):
            gone.add(str(note["id"]))
        note.decompose()
    if not gone:
        return documents, 0
    for _, root in documents:
        for anchor in root.find_all("a", class_="anchor"):
            if str(anchor.get("href", "")).rpartition("#")[2] in gone:
                anchor.decompose()
    if not page[1].find(class_="annotation"):
        # nothing under "Przypisy:" any more; the heading alone is not a chapter
        documents = [d for d in documents if d is not page]
    return documents, len(gone)


def _work_titles(root: Tag) -> list[Tag]:
    return root.find_all(list(HEADING_TAGS), class_=WORK_TITLE)


def _join_works(documents: list[Document]) -> tuple[list[Document], int]:
    """In a collection, bring every work's pages together and keep its sections inside it."""

    if sum(1 for _, root in documents if _work_titles(root)) < 2:
        return documents, 0
    joined: list[Document] = []
    works: list[Tag] = []
    work: Tag | None = None
    moved = 0
    for name, root in documents:
        if not TEXT_PAGE.match(PurePosixPath(name).name):
            joined.append((name, root))
            work = None
        elif _work_titles(root):
            joined.append((name, root))
            works.append(root)
            work = root
        elif work is not None:
            for child in list(root.children):
                work.append(child.extract())
            moved += 1
        else:
            joined.append((name, root))  # ahead of the first work: the collection's own title
    for root in works:
        for title in _work_titles(root):
            _take_subtitle(title)
        for heading in root.find_all(list(HEADING_TAGS)):
            if not {WORK_TITLE, WORK_SUBTITLE} & set(heading.get("class") or []):
                heading.name = SECTION_TAG
    return joined, moved


def _take_subtitle(title: Tag) -> None:
    """ "Traktat o Manekinach" and "Ciąg dalszy" under it are one title, as the library lists it."""

    following = title.find_next_sibling()
    if not isinstance(following, Tag) or following.name not in HEADING_TAGS:
        return
    if WORK_SUBTITLE not in (following.get("class") or []):
        return
    subtitle = normalize_text(following)
    following.decompose()
    if subtitle:
        ends = normalize_text(title)[-1:] in ".?!…:"
        title.append(NavigableString(f"{'' if ends else '.'} {subtitle}"))
