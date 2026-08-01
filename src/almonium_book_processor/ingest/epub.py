"""Primary EPUB source adapter."""

from __future__ import annotations

from pathlib import Path

from ebooklib import ITEM_DOCUMENT, epub

from almonium_book_processor import __version__
from almonium_book_processor.ingest.common import (
    BlockBuilder,
    epub_image_resolver,
    extract_blocks,
    parse_html,
    sha256_file,
)
from almonium_book_processor.models import (
    BookArtifact,
    EditionMetadata,
    IngestionWarning,
    SourceMetadata,
)


def _metadata_value(book: epub.EpubBook, name: str) -> str | None:
    values = book.get_metadata("DC", name)
    if not values:
        return None
    value = values[0][0]
    return str(value).strip() or None


def ingest_epub(
    path: str | Path,
    *,
    edition_id: str,
    work_id: str,
    title: str | None = None,
    author: str | None = None,
    language: str | None = None,
    edition_type: str = "original",
    source_edition_id: str | None = None,
    cefr_target: str | None = None,
    expected_chapters: int | None = None,
) -> BookArtifact:
    """Read an EPUB's declared spine order into normalized content blocks."""

    source_path = Path(path)
    book = epub.read_epub(str(source_path), options={"ignore_ncx": True})
    title = title or _metadata_value(book, "title")
    author = author or _metadata_value(book, "creator")
    language = language or _metadata_value(book, "language")
    missing = [
        name
        for name, value in (("title", title), ("author", author), ("language", language))
        if not value
    ]
    if missing:
        raise ValueError(f"EPUB metadata is missing {', '.join(missing)}; provide an override")

    builder = BlockBuilder(edition_id)
    chapter = 0
    seen_documents: set[str] = set()
    for spine_entry in book.spine:
        item_id = spine_entry[0] if isinstance(spine_entry, tuple) else spine_entry
        item = book.get_item_with_id(item_id)
        if item is None or item.get_type() != ITEM_DOCUMENT:
            continue
        if isinstance(item, epub.EpubNav) or "nav" in getattr(item, "properties", []):
            continue
        document_name = item.get_name()
        if document_name in seen_documents:
            continue
        seen_documents.add(document_name)

        soup = parse_html(item.get_content())
        root = soup.body or soup
        previous_count = len(builder.blocks)
        extract_blocks(
            root,
            chapter=chapter,
            source_name=document_name,
            builder=builder,
            resolve_image=epub_image_resolver(document_name),
        )
        if len(builder.blocks) == previous_count:
            builder.warnings.append(
                IngestionWarning(
                    code="empty_spine_document",
                    message="Spine document contained no supported content blocks",
                    source_ref=document_name,
                    chapter=chapter,
                )
            )
            continue
        chapter += 1

    if not builder.blocks:
        raise ValueError("EPUB contains no supported content blocks")

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
            edition_id=edition_id,
            work_id=work_id,
            title=title,
            author=author,
            language=language,
            edition_type=edition_type,
            source_edition_id=source_edition_id,
            cefr_target=cefr_target,
            source=SourceMetadata(
                format="epub",
                path=str(source_path),
                sha256=sha256_file(source_path),
                identifier=_metadata_value(book, "identifier"),
            ),
        ),
        blocks=builder.blocks,
        warnings=builder.warnings,
    )
