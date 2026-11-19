"""Printed pagination identified by the source markup."""

import re

from bs4 import Tag

from almonium_book_processor.ingest.common import PAGE_MARKERS, marker_values

_MARKERS = PAGE_MARKERS | {"tei-pb", "pagebreak", "doc-pagebreak"}
_LABEL = re.compile(
    r"(?:\[\s*)?(?:(?:p(?:g|age)?\.?|seite)\s+)?(?:\d{1,5}|[ivxlcdm]+)(?:\s*\])?",
    re.IGNORECASE,
)
# Short-circuit the catalogue scan before parsing documents with no page markup.
MARKUP_HINT = re.compile(rb"pagenum|pageno|page-number|folio|tei-pb|pagebreak|page_", re.IGNORECASE)


def page_markers(root: Tag) -> list[Tag]:
    marks = []
    for tag in root.find_all(True):
        if not (marker_values(tag) & _MARKERS or tag.get("id", "").startswith("Page_")):
            continue
        label = tag.get_text().strip()
        if not label or _LABEL.fullmatch(label):
            marks.append(tag)
    return marks


def remove_page_markers(root: Tag) -> None:
    for tag in reversed(page_markers(root)):
        tag.decompose()
