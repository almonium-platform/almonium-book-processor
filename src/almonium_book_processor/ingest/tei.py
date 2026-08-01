"""TEI P5 source adapter, including the ELTeC customization."""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path
from xml.etree.ElementTree import Element

from defusedxml import ElementTree

from almonium_book_processor import __version__
from almonium_book_processor.ingest.common import BlockBuilder, sha256_file
from almonium_book_processor.models import (
    BlockType,
    BookArtifact,
    EditionMetadata,
    IngestionWarning,
    SourceMetadata,
)

TEI_NAMESPACE = "http://www.tei-c.org/ns/1.0"
XML_NAMESPACE = "http://www.w3.org/XML/1998/namespace"
XML_ID = f"{{{XML_NAMESPACE}}}id"
XML_LANG = f"{{{XML_NAMESPACE}}}lang"
NS = {"tei": TEI_NAMESPACE}


def _local_name(element: Element) -> str:
    return element.tag.rsplit("}", 1)[-1]


def _normalized_text(element: Element) -> str:
    return re.sub(r"\s+", " ", "".join(element.itertext())).strip()


def _first_text(root: Element, path: str) -> str | None:
    element = root.find(path, NS)
    if element is None:
        return None
    return _normalized_text(element) or None


def _sections(text: Element) -> list[Element]:
    """Flatten structural wrappers while retaining their own headings/content."""

    sections: list[Element] = []
    content_tags = {
        "head",
        "p",
        "quote",
        "lg",
        "l",
        "note",
        "sp",
        "opener",
        "closer",
        "trailer",
        "figure",
        "milestone",
        "space",
    }

    def collect(container: Element) -> None:
        divisions = [child for child in container if _local_name(child) == "div"]
        if any(_local_name(child) in content_tags for child in container):
            sections.append(container)
        for division in divisions:
            collect(division)

    for part_name in ("front", "body", "back"):
        part = text.find(f"tei:{part_name}", NS)
        if part is not None:
            collect(part)
    return sections


def _extract_section(
    section: Element,
    *,
    chapter: int,
    source_name: str,
    builder: BlockBuilder,
) -> None:
    references: Counter[str] = Counter()

    def source_ref(element: Element) -> str:
        tag = _local_name(element)
        identifier = element.get(XML_ID)
        if identifier:
            return f"{source_name}#{identifier}"
        references[tag] += 1
        return f"{source_name}:{chapter}:{tag}:{references[tag]}"

    def attributes(element: Element, **extra: object) -> dict[str, object]:
        values: dict[str, object] = {"tei_element": _local_name(element)}
        if element.get("type"):
            values["tei_type"] = element.get("type")
        values.update(extra)
        return values

    def add_text(element: Element, block_type: BlockType, **extra: object) -> None:
        builder.add(
            chapter=chapter,
            block_type=block_type,
            text=_normalized_text(element),
            source_ref=source_ref(element),
            attributes=attributes(element, **extra),
        )

    def visit(element: Element) -> None:
        tag = _local_name(element)

        if tag in {"pb", "lb", "fw"}:
            return
        if tag == "div":
            return  # Nested divisions are emitted as their own sections.
        if tag == "head":
            add_text(element, BlockType.HEADING, level=1)
            return
        if tag == "p":
            add_text(element, BlockType.PARAGRAPH)
            return
        if tag in {"quote", "lg"}:
            lines = [
                _normalized_text(line)
                for line in element.iter()
                if _local_name(line) == "l" and _normalized_text(line)
            ]
            if lines:
                builder.add(
                    chapter=chapter,
                    block_type=BlockType.VERSE_STANZA,
                    text="\n".join(lines),
                    source_ref=source_ref(element),
                    attributes=attributes(element, line_count=len(lines), quoted=tag == "quote"),
                )
                if tag == "quote":
                    for paragraph in element.iter():
                        if _local_name(paragraph) == "p":
                            add_text(paragraph, BlockType.EPIGRAPH, role="attribution")
            else:
                add_text(element, BlockType.BLOCKQUOTE)
            return
        if tag == "l":
            add_text(element, BlockType.VERSE_LINE)
            return
        if tag == "note":
            add_text(element, BlockType.FOOTNOTE)
            return
        if tag in {"sp", "speaker", "stage"}:
            add_text(element, BlockType.DIALOGUE)
            return
        if tag in {"opener", "closer", "signed", "dateline", "salute", "postscript"}:
            add_text(element, BlockType.LETTER)
            return
        if tag == "trailer":
            add_text(element, BlockType.PARAGRAPH)
            return
        if tag == "figure":
            graphics = [child for child in element.iter() if _local_name(child) == "graphic"]
            for graphic in graphics:
                image_ref = graphic.get("url") or graphic.get("target")
                if image_ref:
                    builder.add(
                        chapter=chapter,
                        block_type=BlockType.IMAGE,
                        text=_normalized_text(element),
                        source_ref=image_ref,
                        attributes=attributes(element),
                    )
                else:
                    builder.warnings.append(
                        IngestionWarning(
                            code="image_without_source",
                            message="Skipped TEI graphic without a url or target",
                            source_ref=source_ref(graphic),
                            chapter=chapter,
                        )
                    )
            if graphics:
                return
        if tag in {"milestone", "space"}:
            builder.add(
                chapter=chapter,
                block_type=BlockType.SEPARATOR,
                source_ref=source_ref(element),
                attributes=attributes(element),
            )
            return

        for child in element:
            visit(child)

    for child in section:
        visit(child)


def ingest_tei(
    path: str | Path,
    *,
    edition_slug: str,
    work_slug: str,
    title: str | None = None,
    author: str | None = None,
    language: str | None = None,
    edition_type: str = "original",
    source_edition_slug: str | None = None,
    cefr_target: str | None = None,
    expected_chapters: int | None = None,
) -> BookArtifact:
    """Normalize a TEI P5 document without evaluating external entities."""

    source_path = Path(path)
    root = ElementTree.parse(source_path).getroot()
    if root.tag != f"{{{TEI_NAMESPACE}}}TEI":
        raise ValueError("XML source is not a TEI P5 document")

    title = title or _first_text(root, ".//tei:titleStmt/tei:title")
    author = author or _first_text(root, ".//tei:titleStmt/tei:author")
    language = language or root.get(XML_LANG)
    if not language:
        language_element = root.find(".//tei:langUsage/tei:language", NS)
        if language_element is not None:
            language = language_element.get("ident") or _normalized_text(language_element)
    missing = [
        name
        for name, value in (("title", title), ("author", author), ("language", language))
        if not value
    ]
    if missing:
        raise ValueError(f"TEI metadata is missing {', '.join(missing)}; provide an override")

    text = root.find("tei:text", NS)
    if text is None:
        raise ValueError("TEI document has no text element")
    sections = _sections(text)
    if not sections:
        raise ValueError("TEI document contains no supported text sections")

    builder = BlockBuilder(edition_slug)
    for chapter, section in enumerate(sections):
        previous_count = len(builder.blocks)
        _extract_section(
            section,
            chapter=chapter,
            source_name=source_path.name,
            builder=builder,
        )
        if len(builder.blocks) == previous_count:
            builder.warnings.append(
                IngestionWarning(
                    code="empty_tei_section",
                    message="TEI section contained no supported content blocks",
                    source_ref=f"{source_path.name}:section:{chapter}",
                    chapter=chapter,
                )
            )

    if not builder.blocks:
        raise ValueError("TEI document contains no supported content blocks")
    actual_chapters = len({block.chapter for block in builder.blocks})
    if expected_chapters is not None and actual_chapters != expected_chapters:
        builder.warnings.append(
            IngestionWarning(
                code="unexpected_chapter_count",
                message=f"Expected {expected_chapters} chapters, found {actual_chapters}",
                source_ref=str(source_path),
            )
        )

    return BookArtifact(
        processor_version=__version__,
        edition=EditionMetadata(
            edition_slug=edition_slug,
            work_slug=work_slug,
            title=title,
            author=author,
            language=language,
            edition_type=edition_type,
            source_edition_slug=source_edition_slug,
            cefr_target=cefr_target,
            source=SourceMetadata(
                format="tei",
                path=str(source_path),
                sha256=sha256_file(source_path),
                identifier=root.get(XML_ID),
            ),
        ),
        blocks=builder.blocks,
        warnings=builder.warnings,
    )
