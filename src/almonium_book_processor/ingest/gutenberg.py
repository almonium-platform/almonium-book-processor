"""Cut Project Gutenberg's header and licence out of an EPUB before extraction.

A Gutenberg file wraps the book in its own text: a header ending in a
``*** START OF THE PROJECT GUTENBERG EBOOK ... ***`` line and a licence that
begins at ``*** END OF THE PROJECT GUTENBERG EBOOK ... ***`` (older files
also close the book with an ``End of Project Gutenberg's ...`` paragraph
first). None of it is the book, and reading it in only produced a review
item the editor could not act on. The markers are the boundary: everything
before the start marker and everything from the end marker on is dropped,
whole documents included.
"""

from __future__ import annotations

import re

from bs4 import NavigableString, Tag

from almonium_book_processor.models import IngestionWarning

START_MARKER = re.compile(r"\*{3}\s*START OF (?:THE|THIS) PROJECT GUTENBERG", re.IGNORECASE)
END_MARKER = re.compile(
    r"\*{3}\s*END OF (?:THE|THIS) PROJECT GUTENBERG|^[ \t]*End of (?:the )?Project Gutenberg",
    re.IGNORECASE | re.MULTILINE,
)

Document = tuple[str, Tag]


def trim_gutenberg_boilerplate(
    documents: list[Document],
) -> tuple[list[Document], list[IngestionWarning]]:
    """Return the documents that hold the book itself, cut at the Gutenberg markers.

    The roots of the boundary documents are edited in place. A document left
    with nothing but the marker's empty wrapper is dropped rather than reported
    as an unreadable page.
    """

    start = next(
        (
            index
            for index in range(len(documents) - 1, -1, -1)
            if _holds(documents[index], START_MARKER)
        ),
        None,
    )
    end = next(
        (
            index
            for index in range((start or 0), len(documents))
            if _holds(documents[index], END_MARKER)
        ),
        None,
    )
    if start is None and end is None:
        return documents, []

    warnings: list[IngestionWarning] = []
    kept = documents[start if start is not None else 0 : end + 1 if end is not None else None]
    if start is not None:
        _cut_at(kept[0][1], START_MARKER, keep_after=True)
        warnings.append(
            IngestionWarning(
                code="gutenberg_boilerplate_trimmed",
                message=(
                    "Dropped the Project Gutenberg header before the start marker"
                    + (f" and the {start} document(s) ahead of it" if start else "")
                ),
                source_ref=kept[0][0],
            )
        )
    if end is not None:
        _cut_at(kept[-1][1], END_MARKER, keep_after=False)
        trailing = len(documents) - end - 1
        warnings.append(
            IngestionWarning(
                code="gutenberg_boilerplate_trimmed",
                message=(
                    "Dropped the Project Gutenberg licence from the end marker on"
                    + (f" and the {trailing} document(s) after it" if trailing else "")
                ),
                source_ref=kept[-1][0],
            )
        )
    return [document for document in kept if _has_content(document[1])], warnings


def _holds(document: Document, marker: re.Pattern[str]) -> bool:
    return marker.search(document[1].get_text("\n")) is not None


def _has_content(root: Tag) -> bool:
    return bool(root.get_text(strip=True)) or root.find(["img", "image"]) is not None


def _cut_at(root: Tag, marker: re.Pattern[str], *, keep_after: bool) -> None:
    """Remove everything on one side of the marker line, in document order.

    The marker may share a text node with the book (an old header is one
    ``<pre>``), so the node is cut at the marker's line first, and then every
    sibling on the discarded side is removed at each level up to the root.
    """

    node = root.find(string=marker)
    if not isinstance(node, NavigableString):
        return
    match = marker.search(node)
    assert match is not None
    if keep_after:
        line_end = node.find("\n", match.end())
        remainder = "" if line_end == -1 else node[line_end + 1 :]
    else:
        remainder = node[: node.rfind("\n", 0, match.start()) + 1]
    anchor = NavigableString(remainder)
    node.replace_with(anchor)

    current: Tag | NavigableString | None = anchor
    while current is not None and current is not root:
        siblings = list(current.previous_siblings if keep_after else current.next_siblings)
        for sibling in siblings:
            sibling.extract()
        current = current.parent
    if remainder.strip():
        return
    # The marker's own wrapper is empty now; take it out too, or the empty
    # paragraph it leaves behind is reported as skipped.
    parent = anchor.parent
    anchor.extract()
    while isinstance(parent, Tag) and parent is not root and not _has_content(parent):
        empty, parent = parent, parent.parent
        empty.extract()
