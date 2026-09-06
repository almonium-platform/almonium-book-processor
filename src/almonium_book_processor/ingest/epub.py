"""Primary EPUB source adapter."""

from __future__ import annotations

from pathlib import Path

from bs4 import Tag
from ebooklib import ITEM_COVER, ITEM_DOCUMENT, epub

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


def _cover_image_names(book: epub.EpubBook) -> set[str]:
    """Names of the images the EPUB itself declares as its cover."""

    return {item.get_name() for item in book.get_items_of_type(ITEM_COVER)} | {
        item.get_name()
        for item in book.get_items()
        if "cover-image" in (getattr(item, "properties", None) or [])
    }


def _image_sources(root: Tag) -> set[str]:
    sources = {str(tag.get("src", "")).strip() for tag in root.find_all("img")}
    sources |= {
        str(tag.get("xlink:href") or tag.get("href") or "").strip()
        for tag in root.find_all("image")
    }
    return {source for source in sources if source}


def _is_cover_document(root: Tag, document_name: str, cover_images: set[str]) -> bool:
    """True when a spine document does nothing but display the declared cover.

    Almonium renders its own cover from the work's metadata, so this page is
    not content. Recognising it keeps the importer from reporting the book's
    first page as unreadable.
    """

    if not cover_images or root.get_text(strip=True):
        return False
    resolve = epub_image_resolver(document_name)
    references = {resolve(source) for source in _image_sources(root)}
    return bool(references) and references <= cover_images


def ingest_epub(
    path: str | Path,
    *,
    edition_slug: str,
    work_slug: str,
    title: str | None = None,
    author: str | None = None,
    language: str | None = None,
    edition_type: str = "original",
    source_edition_slug: str | None = None,
    cefr_level: str | None = None,
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

    builder = BlockBuilder(edition_slug)
    chapter = 0
    seen_documents: set[str] = set()
    cover_images = _cover_image_names(book)
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
        if _is_cover_document(root, document_name, cover_images):
            builder.warnings.append(
                IngestionWarning(
                    code="cover_document_skipped",
                    message="Skipped the cover page; Almonium renders its own cover",
                    source_ref=document_name,
                    chapter=chapter,
                )
            )
            continue
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
            edition_slug=edition_slug,
            work_slug=work_slug,
            title=title,
            author=author,
            language=language,
            edition_type=edition_type,
            source_edition_slug=source_edition_slug,
            cefr_level=cefr_level,
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
