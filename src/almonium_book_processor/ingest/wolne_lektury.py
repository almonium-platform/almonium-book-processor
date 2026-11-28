"""Cut what is Wolne Lektury's own out of an EPUB before extraction.

The Polish library (wolnelektury.pl, Fundacja Wolne Lektury) exports the text as one document
with the chapters at its headings, and around it its own pages: a title page that also asks for
support, fundraising pages between the chapters (``fund0.xhtml`` …), a support page, and an
editorial page with the licence. None of it is the book.

Nor are the library's notes. The author's text is in the public domain; the notes the library's
editors wrote ("[przypis edytorski]", 349 of them on Sklepy cynamonowe) are theirs, under the
Licencja Wolnej Sztuki, and their numbers stand in the text glued to the words: "Pomona1 z ognia
dnia rozżagwionego2". Every note the author did not write goes, and its number with it. The
author's own notes ("[przypis autorski]", 57 in W pustyni i w puszczy: "Szlachetna26 Fatma")
are the book: each is set as a footnote under the paragraph it belongs to, and its number goes
too, so no page of numbered notes is left at the end.

A collection is exported with each work's title on a page of its own and each numbered section
of a work on the next pages, every one of them a chapter to the splitter: Sierpień came in as
chapters "1", "2" and "3". In a collection a work is one chapter under its own title.

A blank line between paragraphs (``p.spacer``) is the author's break. Król Maciuś Pierwszy has
no chapter headings at all, only 53 such breaks seven to ten thousand characters apart: its
chapters. They came in as empty paragraphs and were dropped, and the book was cut by size into
22 pieces of 150 paragraphs. A text with no headings is cut at its breaks where they make
chapters; every other break stays in the text as a separator.

A story in numbered parts may leave its first part unnumbered: Latarnik opens under its title
and goes on at "II". A chapter named after its book is read as a title page, so the first 43%
of the story stood outside its level. The first part gets the number it lacks.
"""

from __future__ import annotations

import re
from pathlib import PurePosixPath
from urllib.parse import urlsplit

from bs4 import BeautifulSoup, NavigableString, Tag
from ebooklib import epub

from almonium_book_processor.ingest.common import HEADING_TAGS, normalize_text
from almonium_book_processor.models import IngestionWarning

Document = tuple[str, Tag]
LIBRARY_PAGES = re.compile(r"^(fund\d*|support|last|title)\.x?html$")
NOTES_PAGE = "annotations.xhtml"
TEXT_PAGE = re.compile(r"^part\d+\.x?html$")
AUTHORS_NOTE = "[przypis autorski]"
# what a note hangs under: the paragraph, heading or line its number stands in
NOTE_HOSTS = ["p", "li", "blockquote", *sorted(HEADING_TAGS)]
_NOTE_NUMBER = re.compile(r"^\s*\d+\s*\.\s*")
# librarian's EPUB stylesheet: a work's title inside a collection, and the line under it
WORK_TITLE = "intitle"
WORK_SUBTITLE = "insubtitle"
# the one heading the chapter splitter never cuts at: a section inside its chapter
SECTION_TAG = "h6"
# the author's break: a blank line between paragraphs
BREAK = "spacer"
# breaks are chapters when a text with no headings has this many, this far apart, and none
# of the pieces is so long that the next would be read as its continuation
MIN_BREAKS = 5
CHAPTER_SIZED_CHARS = 3_000
LONGEST_CHAPTER_CHARS = 25_000
# a piece this short is a preface or a closing line; it stays with the chapter beside it
SHORT_PIECE_CHARS = 1_500
# the number a first part lacks, by the number the second part carries
FIRST_PART = {"II": "I", "2": "1"}


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
                    "numbers in the text; the author's own notes stand under their paragraphs"
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
    else:
        kept = _number_first_part(kept)
        kept, chapters = _cut_at_breaks(kept)
        if chapters:
            warnings.append(
                IngestionWarning(
                    code="wolne_lektury_cut_at_breaks",
                    message=(
                        f"Cut a text with no chapter headings into {chapters} chapters at "
                        "the blank lines its author set between them"
                    ),
                )
            )
    for _, root in kept:
        for spacer in root.find_all("p", class_=BREAK):
            spacer.replace_with(_separator())
    return kept, warnings


def _drop_library_notes(documents: list[Document]) -> tuple[list[Document], int]:
    """Take out every note the author did not write; set the author's under their paragraphs."""

    page = next((d for d in documents if PurePosixPath(d[0]).name == NOTES_PAGE), None)
    if page is None:
        return documents, 0
    gone: set[str] = set()
    kept: dict[str, Tag] = {}
    for note in page[1].find_all(class_="annotation"):
        if AUTHORS_NOTE in note.get_text() and note.get("id"):
            kept[str(note["id"])] = note
            continue
        if note.get("id"):
            gone.add(str(note["id"]))
        note.decompose()
    if not gone and not kept:
        return documents, 0
    placed: dict[int, Tag] = {}  # the last note set under each host, so two keep their order
    for _, root in documents:
        if root is page[1]:
            continue
        for anchor in root.find_all("a", class_="anchor"):
            target = str(anchor.get("href", "")).rpartition("#")[2]
            if target in gone:
                anchor.decompose()
            elif target in kept and (host := anchor.find_parent(NOTE_HOSTS)) is not None:
                footnote = _footnote(kept.pop(target))
                placed.get(id(host), host).insert_after(footnote)
                placed[id(host)] = footnote
                anchor.decompose()
    if not page[1].find(class_="annotation"):
        # nothing under "Przypisy:" any more; the heading alone is not a chapter
        documents = [d for d in documents if d is not page]
    return documents, len(gone)


def _footnote(note: Tag) -> Tag:
    """The author's words alone: without the library's number, link back and label."""

    text = _NOTE_NUMBER.sub("", normalize_text(note)).replace(AUTHORS_NOTE, "").strip()
    note.decompose()
    footnote = BeautifulSoup("", "html.parser").new_tag("aside")
    footnote.string = text
    return footnote


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


def _separator() -> Tag:
    return BeautifulSoup("", "html.parser").new_tag("hr")


def _text_chars(nodes: list) -> int:
    return sum(
        len(normalize_text(node)) if isinstance(node, Tag) else len(str(node).strip())
        for node in nodes
    )


def _cut_at_breaks(documents: list[Document]) -> tuple[list[Document], int]:
    """Make a chapter of each piece between the author's breaks, in a text with no headings."""

    pages = [d for d in documents if TEXT_PAGE.match(PurePosixPath(d[0]).name)]
    if len(pages) != 1:
        return documents, 0
    name, root = pages[0]
    titles = [
        heading
        for heading in root.find_all(list(HEADING_TAGS))
        if {WORK_TITLE, WORK_SUBTITLE} & set(heading.get("class") or [])
    ]
    if len(titles) != len(root.find_all(list(HEADING_TAGS))):
        return documents, 0  # it has headings of its own; the splitter reads those
    breaks = root.find_all("p", class_=BREAK)
    if len(breaks) < MIN_BREAKS or any(b.parent is not breaks[0].parent for b in breaks):
        return documents, 0
    container = breaks[0].parent
    if any(title.parent is not container for title in titles):
        return documents, 0
    pieces: list[list] = [[]]
    for child in list(container.children):
        if child in breaks:
            pieces.append([])
        elif child not in titles:
            pieces[-1].append(child)
    pieces = [piece for piece in pieces if _text_chars(piece)]
    sizes = sorted(_text_chars(piece) for piece in pieces)
    if (
        len(pieces) <= MIN_BREAKS
        or sizes[len(sizes) // 2] < CHAPTER_SIZED_CHARS
        or sizes[-1] > LONGEST_CHAPTER_CHARS
    ):
        return documents, 0

    chapters: list[list] = []
    opening: list = []  # a short piece ahead of the first chapter opens it
    for piece in pieces:
        if _text_chars(piece) >= SHORT_PIECE_CHARS:
            chapters.append([*opening, *([_separator()] if opening else []), *piece])
            opening = []
        elif chapters:
            chapters[-1].extend([_separator(), *piece])
        else:
            opening.extend(piece)
    cut: list[Document] = []
    if titles:
        # a page of its own, so the title labels the book and names no chapter
        page = Tag(name="div")
        for title in titles:
            page.append(title.extract())
        cut.append((name, page))
    for chapter in chapters:
        part = Tag(name="div")
        for child in chapter:
            part.append(child.extract() if child.parent is not None else child)
        cut.append((name, part))
    at = documents.index(pages[0])
    return [*documents[:at], *cut, *documents[at + 1 :]], len(chapters)


def _is_title(heading: Tag) -> bool:
    return bool({WORK_TITLE, WORK_SUBTITLE} & set(heading.get("class") or []))


def _number_first_part(documents: list[Document]) -> list[Document]:
    """Give the part a story opens with, under its title alone, the number it was left without."""

    pages = [d for d in documents if TEXT_PAGE.match(PurePosixPath(d[0]).name)]
    headings = [h for _, root in pages for h in root.find_all(list(HEADING_TAGS))]
    titles = [heading for heading in headings if _is_title(heading)]
    parts = [heading for heading in headings if not _is_title(heading)]
    if not titles or not parts or headings[: len(titles)] != titles:
        return documents
    number = FIRST_PART.get(normalize_text(parts[0]))
    opening = titles[-1].find_next(["p", *sorted(HEADING_TAGS)])
    if number is None or opening is None or opening.name != "p":
        return documents  # no prose under the title, or the parts are not plain numbers
    first = BeautifulSoup("", "html.parser").new_tag(parts[0].name)
    first["class"] = parts[0].get("class") or []
    first.string = number
    titles[-1].insert_after(first)
    # a page of its own, so the title labels the book and the first part is named by its number
    home = next(d for d in pages if titles[0] in d[1].find_all(list(HEADING_TAGS)))
    page = Tag(name="div")
    for title in titles:
        page.append(title.extract())
    at = documents.index(home)
    return [*documents[:at], (home[0], page), *documents[at:]]
