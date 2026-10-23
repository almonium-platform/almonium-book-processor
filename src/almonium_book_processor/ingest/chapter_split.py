"""Cut a spine document that holds several chapters at its chapter headings.

Project Gutenberg's EPUBs do not give every chapter its own document: a long
book is sawn into ``-h-0``, ``-h-1``, ... files of roughly 150,000 characters
each, and a short one is a single file. The chapters inside are plain ``<h2>``
siblings of the paragraphs (``-I- Perdido``, ``I.``, ``LE CRIME AU PÈRE
BONIFACE``), so reading one document as one chapter leaves the reader a
120,000-character page and the adaptation probe nothing under its limit.

A document is cut where a chapter heading stands: an ``h1``-``h3``, or a
paragraph that is nothing but a chapter label (``CAPÍTULO I``, ``II.``,
``Kapitel 3: Der Aufbruch``) or is marked as a heading by its class. A run of
headings with no prose between them (a part title over its first chapter, a
title page's author and title lines) is one chapter, named after its first
heading. Cuts are made at the heading level most of the document's chapters
use and at shallower ones, so a numbered section inside a story (``<p>II</p>``
under an ``<h2>`` story title) does not become a chapter of its own. Nothing is
cut inside a table, verse, a quotation or a footnote, and a document shorter
than a title page is never cut at all.

Gutenberg saws the files by size, not at chapter ends, so the next file opens in
the middle of a chapter. :func:`opens_without_heading` lets the adapter attach
that opening to the chapter the previous file ended in.
"""

from __future__ import annotations

import re

from bs4 import NavigableString, Tag

from almonium_book_processor.ingest.common import (
    FOOTNOTE_MARKERS,
    HEADING_TAGS,
    LETTER_MARKERS,
    SKIP_TAGS,
    VERSE_MARKERS,
    has_marker,
    marker_values,
    normalize_text,
)

# A document over this length is cut at every chapter heading it has; a shorter
# one only when it holds at least two chapters, and never under the floor,
# where several headings are a title page, not a book.
LONG_DOCUMENT_CHARS = 25_000
SHORT_DOCUMENT_CHARS = 3_000
# A document this long that stays one chapter is reported for a person to see.
UNSPLIT_DOCUMENT_CHARS = 60_000

# Gutenberg's Portuguese books of 1899 and 1890 (Dom Casmurro, O Cortiço) mark every chapter with an
# h4 and its title with an h5; the level most chapters use is cut at, so a deeper heading only ever
# starts a chapter in a document that has no shallower ones.
CHAPTER_HEADING_TAGS = {"h1", "h2", "h3", "h4", "h5"}
UNSPLITTABLE_TAGS = {"table", "pre", "blockquote", "ul", "ol", "dl", "aside", "figure"} | SKIP_TAGS
UNSPLITTABLE_MARKERS = VERSE_MARKERS | FOOTNOTE_MARKERS | LETTER_MARKERS | {"epigraph", "toc"}
# A paragraph carrying one of these classes is the chapter's heading in styles
# that do not use heading elements.
HEADING_CLASSES = {
    "chapter",
    "chaptertitle",
    "chapter-title",
    "chapterhead",
    "chapter-head",
    "chaphead",
    "heading",
    "titre",
}
MAX_LABEL_CHARS = 120

LABEL_WORDS = (
    r"(?:chapter|chapitre|cap[ií]tulo|capitolo|kapitel|teil|part|partie|parte"
    r"|book|livre|libro|buch|tome|band)"
)
ROMAN = r"(?=[ivxlcdm])m{0,3}(?:cm|cd|d?c{0,3})(?:xc|xl|l?x{0,3})(?:ix|iv|v?i{0,3})"
NUMERAL = rf"(?P<numeral>{ROMAN}|\d{{1,3}})"
# "I.", "-II-", "CAPÍTULO I", "Kapitel 3:" ... and, with a label word, the
# chapter's own title after a separator: "CAPÍTULO I. Perdido".
CHAPTER_LABEL = re.compile(
    rf"^[-–—(\[]*\s*(?:{LABEL_WORDS}\s+)?{NUMERAL}\s*[-–—.)\]:]*$"
    rf"|^{LABEL_WORDS}\s+(?P<labelled>{ROMAN}|\d{{1,3}})\s*[-–—.:]\s*\S.*$",
    re.IGNORECASE,
)


def split_at_chapter_headings(root: Tag) -> list[Tag]:
    """Return the chapters a document holds, in order, or ``[root]`` unchanged.

    The root is edited in place when it is cut: it keeps whatever stands before
    the first chapter heading, and every later chapter is moved into a fresh
    container in document order. Chapter-label paragraphs become ``h2``
    elements then, so the chapter is titled by them instead of repeating them
    as its first paragraph.
    """

    length = document_length(root)
    if length < SHORT_DOCUMENT_CHARS:
        return [root]
    headings = chapter_headings(root)
    if not headings:
        return [root]
    starts, preamble = _chapter_starts(root, headings)
    starts = _at_chapter_level(starts)
    chapters = len(starts) + (1 if preamble else 0)
    if chapters < 2 or (length <= LONG_DOCUMENT_CHARS and len(starts) < 2):
        return [root]

    for heading in headings:
        if heading.name not in HEADING_TAGS:
            heading.name = "h2"
    segments: list[Tag] = []
    for heading in reversed(starts):
        segments.insert(0, _detach_from(heading, root))
    if preamble:
        segments.insert(0, root)
    else:
        # Whitespace or an empty wrapper ahead of the first heading: keep it
        # with the first chapter rather than losing an image that sits there.
        for child in reversed(list(root.children)):
            segments[0].insert(0, child.extract())
    return segments


def document_length(root: Tag) -> int:
    return len(root.get_text(" ", strip=True))


def opens_without_heading(root: Tag) -> bool:
    """True when the document's first words are prose, not a chapter heading."""

    for string in root.find_all(string=True):
        if type(string) is not NavigableString or not string.strip():
            continue
        if not _is_body_text(string, root):
            return False
        return not any(
            isinstance(parent, Tag) and (parent.name in HEADING_TAGS or _is_label(parent))
            for parent in string.parents
        )
    return False


def chapter_headings(root: Tag) -> list[Tag]:
    """The elements a chapter may start at, in document order."""

    found: list[Tag] = []
    for tag in root.find_all(list(CHAPTER_HEADING_TAGS) + ["p", "div"]):
        if _inside_unsplittable(tag, root):
            continue
        if tag.name in CHAPTER_HEADING_TAGS:
            if normalize_text(tag):
                found.append(tag)
        elif _is_label(tag):
            found.append(tag)
    return found


def _inside_unsplittable(tag: Tag, root: Tag) -> bool:
    for parent in tag.parents:
        if parent is root or not isinstance(parent, Tag):
            break
        if parent.name in UNSPLITTABLE_TAGS or has_marker(parent, UNSPLITTABLE_MARKERS):
            return True
    return False


def _is_label(tag: Tag) -> bool:
    """A paragraph that is only a chapter label, or is marked as a heading."""

    if tag.find(["p", "div", "table", "ul", "ol", "blockquote", "pre", *HEADING_TAGS]):
        return False
    text = normalize_text(tag)
    if not text or len(text) > MAX_LABEL_CHARS:
        return False
    if marker_values(tag) & HEADING_CLASSES:
        return True
    match = CHAPTER_LABEL.match(text)
    if match is None:
        return False
    numeral = match.group("numeral") or match.group("labelled")
    # Roman numerals are set in one case; "Mix." is a word, not 1009.
    return numeral.isdigit() or numeral.isupper() or numeral.islower()


def _chapter_starts(root: Tag, headings: list[Tag]) -> tuple[list[Tag], bool]:
    """Which headings begin a chapter, and whether prose stands before the first.

    Walking the text in document order, a heading starts a chapter only when
    something other than headings has been written since the last start; a
    trailing heading with nothing after it stays with the chapter before.
    """

    heading_ids = {id(heading) for heading in headings}
    starts: list[Tag] = []
    body_since_start = False
    preamble = False
    seen_heading = False
    for string in root.find_all(string=True):
        if type(string) is not NavigableString or not string.strip():
            continue
        heading = _enclosing(string, heading_ids, root)
        if heading is not None:
            if not seen_heading or body_since_start:
                if heading is not (starts[-1] if starts else None):
                    starts.append(heading)
                body_since_start = False
            seen_heading = True
            continue
        if _is_body_text(string, root):
            if not seen_heading:
                preamble = True
            body_since_start = True
    if starts and not body_since_start:
        # Headings with nothing after them close the chapter before; when they
        # are all the document has, it is a title page, not chapters.
        starts.pop()
    return starts, preamble


def _at_chapter_level(starts: list[Tag]) -> list[Tag]:
    """Keep the starts at the level most chapters use, and any shallower ones.

    A label paragraph counts as deeper than every heading element: it names
    the chapters only in a document that has no other way of marking them.
    """

    if not starts:
        return starts
    levels = [_level(heading) for heading in starts]
    dominant = max(sorted(set(levels)), key=levels.count)
    return [heading for heading, level in zip(starts, levels, strict=True) if level <= dominant]


def _level(heading: Tag) -> int:
    return int(heading.name[1]) if heading.name in HEADING_TAGS else len(HEADING_TAGS) + 1


def _enclosing(string: NavigableString, heading_ids: set[int], root: Tag) -> Tag | None:
    for parent in string.parents:
        if parent is root or not isinstance(parent, Tag):
            return None
        if id(parent) in heading_ids:
            return parent
    return None


def _is_body_text(string: NavigableString, root: Tag) -> bool:
    for parent in string.parents:
        if parent is root or not isinstance(parent, Tag):
            return True
        if parent.name in HEADING_TAGS or parent.name in SKIP_TAGS:
            return False
    return True


def _detach_from(start: Tag, root: Tag) -> Tag:
    """Move ``start`` and everything after it, up to the root, into a new container."""

    container = Tag(name="div")
    trailing: list[list] = []
    current: Tag | None = start
    while current is not None and current is not root:
        trailing.append(list(current.next_siblings))
        current = current.parent
    container.append(start.extract())
    for siblings in trailing:
        for sibling in siblings:
            container.append(sibling.extract())
    return container
