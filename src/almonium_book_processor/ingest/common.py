"""Shared HTML-to-block extraction used by EPUB and the legacy adapter."""

from __future__ import annotations

import hashlib
import posixpath
import re
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

    def __init__(self, edition_id: str) -> None:
        self.edition_id = edition_id
        self.blocks: list[ContentBlock] = []
        self.warnings: list[IngestionWarning] = []
        self._sequence_by_chapter: dict[int, int] = {}

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
                edition_id=self.edition_id,
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

    def visit(tag: Tag) -> None:
        if tag.name in SKIP_TAGS or tag.get("hidden") is not None:
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

        for child in tag.children:
            if isinstance(child, Tag):
                visit(child)

    visit(root)


def epub_image_resolver(document_name: str) -> Callable[[str], str]:
    base = posixpath.dirname(document_name)

    def resolve(src: str) -> str:
        return posixpath.normpath(posixpath.join(base, src))

    return resolve


def parse_html(content: bytes | str) -> BeautifulSoup:
    return BeautifulSoup(content, "html.parser")
