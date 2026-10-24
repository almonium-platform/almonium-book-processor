"""Shared HTML-to-block extraction used by EPUB and the legacy adapter."""

from __future__ import annotations

import hashlib
import posixpath
import re
import statistics
from collections.abc import Callable
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup, NavigableString, Tag

from almonium_book_processor.models import BlockType, ContentBlock, IngestionWarning

BLOCK_PREFIX = {
    BlockType.PARAGRAPH: "p",
    BlockType.HEADING: "h",
    BlockType.VERSE_LINE: "vl",
    BlockType.VERSE_STANZA: "vs",
    BlockType.BLOCKQUOTE: "bq",
    BlockType.LETTER: "l",
    BlockType.EPIGRAPH: "e",
    BlockType.DIALOGUE: "d",
    BlockType.FOOTNOTE: "fn",
    BlockType.IMAGE: "i",
    BlockType.SEPARATOR: "sep",
}

SKIP_TAGS = {"script", "style", "nav", "noscript", "svg"}
HEADING_TAGS = {"h1", "h2", "h3", "h4", "h5", "h6"}
TEXT_TAGS = {"p", "li", "pre", "figcaption", "dt", "dd"}
FOOTNOTE_MARKERS = {"footnote", "endnote", "rearnote"}
VERSE_MARKERS = {"poem", "poetry", "verse", "stanza"}
LETTER_MARKERS = {"letter", "telegram"}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def normalize_text(tag: Tag) -> str:
    """Keep inline boundaries natural while collapsing layout whitespace."""

    return re.sub(r"\s+", " ", tag.get_text("", strip=False)).strip()


def verse_lines(tag: Tag) -> list[str]:
    """Extract verse without turning inline emphasis into artificial line breaks."""

    parts: list[str] = []

    def collect(node: Tag) -> None:
        for child in node.children:
            if isinstance(child, NavigableString):
                parts.append(str(child))
            elif isinstance(child, Tag):
                if child.name == "br":
                    parts.append("\n")
                else:
                    collect(child)
                    if child.name in {"p", "div", "li"}:
                        parts.append("\n")

    collect(tag)
    lines = [re.sub(r"\s+", " ", line).strip() for line in "".join(parts).splitlines()]
    return [line for line in lines if line]


def marker_values(tag: Tag) -> set[str]:
    values = {value.lower() for value in tag.get("class", [])}
    for attribute in ("epub:type", "type", "role"):
        value = tag.get(attribute)
        if value:
            values.update(part.lower() for part in re.split(r"\s+", str(value)))
    return values


def has_marker(tag: Tag, markers: set[str]) -> bool:
    values = marker_values(tag)
    return bool(values & markers) or any(
        any(marker in value for marker in markers) for value in values
    )


class BlockBuilder:
    """Assign deterministic IDs and chapter-local sequence numbers."""

    def __init__(self, edition_slug: str) -> None:
        self.edition_slug = edition_slug
        self.blocks: list[ContentBlock] = []
        self.warnings: list[IngestionWarning] = []
        self._sequence_by_chapter: dict[int, int] = {}

    def mark(self, chapter: int, *, since: int, **attributes: Any) -> None:
        """Give the blocks added since ``since`` to ``chapter`` these attributes."""

        for index in range(since, len(self.blocks)):
            block = self.blocks[index]
            if block.chapter == chapter:
                self.blocks[index] = block.model_copy(
                    update={"attributes": {**block.attributes, **attributes}}
                )

    def add(
        self,
        *,
        chapter: int,
        block_type: BlockType,
        text: str = "",
        source_ref: str | None = None,
        attributes: dict[str, Any] | None = None,
    ) -> None:
        text = text.strip()
        if not text and block_type not in {BlockType.IMAGE, BlockType.SEPARATOR}:
            self.warnings.append(
                IngestionWarning(
                    code="empty_block_skipped",
                    message=f"Skipped empty {block_type.value} element",
                    source_ref=source_ref,
                    chapter=chapter,
                )
            )
            return

        seq = self._sequence_by_chapter.get(chapter, 0) + 1
        self._sequence_by_chapter[chapter] = seq
        prefix = BLOCK_PREFIX[block_type]
        self.blocks.append(
            ContentBlock(
                edition_slug=self.edition_slug,
                block_id=f"c{chapter}.{prefix}{seq}",
                chapter=chapter,
                seq=seq,
                type=block_type,
                text=text,
                source_ref=source_ref,
                attributes=attributes or {},
            )
        )


def extract_blocks(
    root: Tag,
    *,
    chapter: int,
    source_name: str,
    builder: BlockBuilder,
    resolve_image: Callable[[str], str] | None = None,
) -> None:
    """Walk a content root once, emitting presentation-independent blocks."""

    def reference(tag: Tag) -> str:
        anchor = tag.get("id")
        return f"{source_name}#{anchor}" if anchor else source_name

    def emit_verse(tag: Tag) -> None:
        lines = verse_lines(tag)
        if not lines:
            builder.add(
                chapter=chapter,
                block_type=BlockType.VERSE_STANZA,
                source_ref=reference(tag),
            )
            return
        builder.add(
            chapter=chapter,
            block_type=BlockType.VERSE_STANZA,
            text="\n".join(lines),
            source_ref=reference(tag),
            attributes={"line_count": len(lines)},
        )

    def emit_svg_image(tag: Tag) -> None:
        """Emit the bitmap an <svg> wraps; ignore genuine vector decoration.

        Full-page images are routinely wrapped in an SVG viewport, so skipping
        every <svg> would silently drop illustration plates and leave the page
        looking empty.
        """

        image = tag.find("image")
        href = str(image.get("xlink:href") or image.get("href") or "").strip() if image else ""
        if not href:
            return
        builder.add(
            chapter=chapter,
            block_type=BlockType.IMAGE,
            source_ref=resolve_image(href) if resolve_image else href,
            attributes={
                key: str(image[key]) for key in ("width", "height") if image.get(key) is not None
            },
        )

    def visit(tag: Tag) -> None:
        if tag.get("hidden") is not None:
            return
        if tag.name == "svg":
            emit_svg_image(tag)
            return
        if tag.name in SKIP_TAGS:
            return

        markers = marker_values(tag)
        source_ref = reference(tag)

        if tag.name == "img":
            src = str(tag.get("src", "")).strip()
            if not src:
                builder.warnings.append(
                    IngestionWarning(
                        code="image_without_source",
                        message="Skipped image without a src attribute",
                        source_ref=source_ref,
                        chapter=chapter,
                    )
                )
                return
            image_ref = resolve_image(src) if resolve_image else src
            builder.add(
                chapter=chapter,
                block_type=BlockType.IMAGE,
                text=str(tag.get("alt", "")).strip(),
                source_ref=image_ref,
                attributes={
                    key: str(tag[key])
                    for key in ("alt", "title", "width", "height")
                    if tag.get(key) is not None
                },
            )
            return

        if tag.name == "hr":
            builder.add(
                chapter=chapter,
                block_type=BlockType.SEPARATOR,
                source_ref=source_ref,
            )
            return
        if tag.name == "tr":
            # a row of a book laid out as a table: its cells are one line, a cell that is only
            # a number is the line number of a poem and not its words
            cells = [normalize_text(cell) for cell in tag.find_all(["td", "th"], recursive=False)]
            words = [
                cell for cell in cells if cell and not re.fullmatch(r"[\d.,;:()\[\]\s-]+", cell)
            ]
            if words:
                line = " ".join(words)
                builder.add(
                    chapter=chapter,
                    block_type=BlockType.VERSE_LINE
                    if len(line) < VERSE_LINE_CHARS
                    else BlockType.PARAGRAPH,
                    text=line,
                    source_ref=source_ref,
                )
            else:
                for image in tag.find_all("img"):
                    visit(image)
            return

        if tag.name in HEADING_TAGS:
            builder.add(
                chapter=chapter,
                block_type=BlockType.HEADING,
                text=normalize_text(tag),
                source_ref=source_ref,
                attributes={"level": int(tag.name[1])},
            )
            return

        if tag.name == "aside" or markers & FOOTNOTE_MARKERS or has_marker(tag, FOOTNOTE_MARKERS):
            builder.add(
                chapter=chapter,
                block_type=BlockType.FOOTNOTE,
                text=normalize_text(tag),
                source_ref=source_ref,
            )
            return

        if markers & {"stanza"} or has_marker(tag, {"stanza"}):
            emit_verse(tag)
            return

        if tag.name == "blockquote" or markers & {"blockquote"}:
            builder.add(
                chapter=chapter,
                block_type=BlockType.BLOCKQUOTE,
                text=normalize_text(tag),
                source_ref=source_ref,
            )
            return

        if has_marker(tag, LETTER_MARKERS):
            builder.add(
                chapter=chapter,
                block_type=BlockType.LETTER,
                text=normalize_text(tag),
                source_ref=source_ref,
            )
            return

        if has_marker(tag, {"epigraph"}):
            builder.add(
                chapter=chapter,
                block_type=BlockType.EPIGRAPH,
                text=normalize_text(tag),
                source_ref=source_ref,
            )
            return

        if tag.name in TEXT_TAGS:
            images = tag.find_all("img")
            if images:
                for image in images:
                    visit(image)
                if not normalize_text(tag):
                    return

            if has_marker(tag, VERSE_MARKERS) or any(
                has_marker(parent, VERSE_MARKERS)
                for parent in tag.parents
                if isinstance(parent, Tag)
            ):
                for line in verse_lines(tag):
                    builder.add(
                        chapter=chapter,
                        block_type=BlockType.VERSE_LINE,
                        text=line,
                        source_ref=source_ref,
                    )
                return

            block_type = (
                BlockType.DIALOGUE
                if has_marker(tag, {"dialogue", "speech"})
                else BlockType.PARAGRAPH
            )
            builder.add(
                chapter=chapter,
                block_type=block_type,
                text=normalize_text(tag),
                source_ref=source_ref,
            )
            return

        # a container's own text: Gutenberg's verse and its plain-text-born books put the
        # words straight into a <div>, lines parted by <br> and paragraphs by a blank line,
        # with no <p> anywhere (Os Lusíadas: 2,656 <br> and not one paragraph element)
        loose: list = []
        for child in tag.children:
            if isinstance(child, NavigableString) or (
                isinstance(child, Tag) and (child.name == "br" or child.name in INLINE_TAGS)
            ):
                loose.append(child)
                continue
            emit_loose(loose, tag)
            loose = []
            if isinstance(child, Tag):
                visit(child)
        emit_loose(loose, tag)

    def emit_loose(nodes: list, parent: Tag) -> None:
        for lines in loose_paragraphs(nodes):
            if not lines:
                continue
            if looks_like_verse(lines):
                builder.add(
                    chapter=chapter,
                    block_type=BlockType.VERSE_STANZA,
                    text="\n".join(lines),
                    source_ref=reference(parent),
                    attributes={"line_count": len(lines)},
                )
            else:
                builder.add(
                    chapter=chapter,
                    block_type=BlockType.PARAGRAPH,
                    text=" ".join(lines),
                    source_ref=reference(parent),
                )

    visit(root)


INLINE_TAGS = {
    "a",
    "abbr",
    "b",
    "cite",
    "code",
    "em",
    "i",
    "q",
    "small",
    "span",
    "strong",
    "sub",
    "sup",
    "u",
}
# Lines this short, on the median, are verse; longer ones are prose wrapped at the line.
VERSE_LINE_CHARS = 60


def loose_paragraphs(nodes: list) -> list[list[str]]:
    """The paragraphs in a run of text nodes, <br> and inline tags: lists of lines.

    A paragraph ends at two line breaks in a row or at a blank line in the text itself; a
    line ends at a <br> or at a newline. Comments and whitespace-only runs give nothing.
    """

    pieces: list[str] = []
    for node in nodes:
        if isinstance(node, Tag):
            pieces.append("\n" if node.name == "br" else node.get_text(" "))
        elif type(node) is NavigableString:
            pieces.append(str(node))
    text = "".join(pieces)
    paragraphs: list[list[str]] = []
    for chunk in re.split(r"\n[ \t\r\f\v]*\n", text):
        lines = [re.sub(r"\s+", " ", line).strip() for line in chunk.split("\n")]
        lines = [line for line in lines if line]
        if lines:
            paragraphs.append(lines)
    return paragraphs


def looks_like_verse(lines: list[str]) -> bool:
    if len(lines) < 2:
        return False
    return statistics.median(len(line) for line in lines) < VERSE_LINE_CHARS


def epub_image_resolver(document_name: str) -> Callable[[str], str]:
    base = posixpath.dirname(document_name)

    def resolve(src: str) -> str:
        return posixpath.normpath(posixpath.join(base, src))

    return resolve


def parse_html(content: bytes | str) -> BeautifulSoup:
    return BeautifulSoup(content, "html.parser")


def fold_heading_only_chapters(
    blocks: list[ContentBlock],
) -> tuple[list[ContentBlock], list[IngestionWarning]]:
    """Join every heading-only chapter to the chapter after it, as that chapter's part label.

    The splitter opens a chapter at every heading, so a heading followed at once by another
    heading becomes a chapter of its own title: Zarathustra's "Erster Theil", a poem's title
    ahead of its numbered sections. Such a chapter has headings and at most images, no text.
    Its blocks move to the front of the next chapter; its headings are marked ``part`` so the
    next chapter keeps its own title. The chapters are numbered again from 0 and the block
    ids follow. A heading-only chapter at the very end, a closing word such as "FINE.", joins
    the chapter before it: it is the end of that chapter, not a chapter.
    """

    by_chapter: dict[int, list[ContentBlock]] = {}
    for block in blocks:
        by_chapter.setdefault(block.chapter, []).append(block)
    numbers = sorted(by_chapter)
    groups: list[list[ContentBlock]] = []
    carry: list[ContentBlock] = []
    folded = 0
    for number in numbers:
        group = by_chapter[number]
        heading_only = any(block.type == BlockType.HEADING for block in group) and all(
            block.type in (BlockType.HEADING, BlockType.IMAGE, BlockType.SEPARATOR)
            for block in group
        )
        if heading_only:
            carry.extend(
                block.model_copy(update={"attributes": {**block.attributes, "part": True}})
                if block.type == BlockType.HEADING
                else block
                for block in group
            )
            folded += 1
            continue
        groups.append(carry + group)
        carry = []
    if carry and groups:
        groups[-1].extend(carry)  # the closing word ends the last chapter
    elif carry:
        groups.append(carry)
    if not folded:
        return blocks, []
    renumbered = []
    for chapter, group in enumerate(groups):
        for seq, block in enumerate(group, 1):
            renumbered.append(
                block.model_copy(
                    update={
                        "chapter": chapter,
                        "seq": seq,
                        "block_id": f"c{chapter}.{BLOCK_PREFIX[block.type]}{seq}",
                    }
                )
            )
    return renumbered, [
        IngestionWarning(
            code="heading_only_chapters_folded",
            message=(
                f"{folded} heading-only chapter(s) joined the chapter after them as part labels"
            ),
        )
    ]
