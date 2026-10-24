"""Primary EPUB source adapter."""

from __future__ import annotations

from pathlib import Path

from bs4 import Tag
from ebooklib import ITEM_COVER, ITEM_DOCUMENT, epub

from almonium_book_processor import __version__
from almonium_book_processor.ingest.chapter_split import (
    LONG_DOCUMENT_CHARS,
    SIZE_SPLIT_TARGET_CHARS,
    UNSPLIT_DOCUMENT_CHARS,
    document_length,
    opens_without_heading,
    split_at_chapter_headings,
    split_by_size,
)
from almonium_book_processor.ingest.common import (
    BlockBuilder,
    epub_image_resolver,
    extract_blocks,
    fold_heading_only_chapters,
    parse_html,
    sha256_file,
)
from almonium_book_processor.ingest.gutenberg import trim_gutenberg_boilerplate
from almonium_book_processor.ingest.wikisource import (
    is_wikisource_export,
    trim_wikisource_matter,
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
    missing = [name for name, value in (("title", title), ("language", language)) if not value]
    if missing:
        raise ValueError(f"EPUB metadata is missing {', '.join(missing)}; provide an override")
    # anthologies, anonymous works and scripture name no author; the book is still a book,
    # and the metadata step proposes one afterwards
    author_missing = not author
    author = author or "Unknown"

    documents: list[tuple[str, Tag]] = []
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
        documents.append((document_name, soup.body or soup))

    builder = BlockBuilder(edition_slug)
    if author_missing:
        builder.warnings.append(
            IngestionWarning(
                code="author_missing",
                message="The EPUB names no author; 'Unknown' stands until one is entered",
                source_ref=str(source_path),
            )
        )
    documents, notices = trim_gutenberg_boilerplate(documents)
    builder.warnings.extend(notices)
    if is_wikisource_export(book):
        documents, notices = trim_wikisource_matter(documents)
        builder.warnings.extend(notices)
    chapter = 0
    cover_images = _cover_image_names(book)
    # Gutenberg cuts a long book into files by size, mid-chapter; a file that
    # opens in prose right after a long one continues the chapter it ended in.
    previous_was_long = False
    for document_name, root in documents:
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
        first_chapter = chapter
        length = document_length(root)
        continues = previous_was_long and chapter > 0 and opens_without_heading(root)
        previous_was_long = length > LONG_DOCUMENT_CHARS
        segments = split_at_chapter_headings(root)
        # a chapter longer than a long document is cut by size, headings or none: Damiano's
        # four files of 170,000 characters each had a heading or two and no chapters
        sized: list[Tag] = []
        cut_by_size: set[int] = set()
        by_size = 0
        for segment in segments:
            parts = (
                split_by_size(segment)
                if document_length(segment) > UNSPLIT_DOCUMENT_CHARS
                else [segment]
            )
            by_size += len(parts) - 1
            if len(parts) > 1:
                cut_by_size.update(range(len(sized), len(sized) + len(parts)))
            sized.extend(parts)
        segments = sized
        for index, segment in enumerate(segments):
            previous_count = len(builder.blocks)
            target_chapter = chapter - 1 if continues and index == 0 else chapter
            extract_blocks(
                segment,
                chapter=target_chapter,
                source_name=document_name,
                builder=builder,
                resolve_image=epub_image_resolver(document_name),
            )
            if index in cut_by_size:
                # the parts of a text cut by size are the story, whatever they are called
                builder.mark(target_chapter, since=previous_count, cut="size")
            if len(builder.blocks) > previous_count and not (continues and index == 0):
                chapter += 1
        produced = chapter - first_chapter
        if continues and len(segments) == 1:
            continue
        if not produced:
            builder.warnings.append(
                IngestionWarning(
                    code="empty_spine_document",
                    message="Spine document contained no supported content blocks",
                    source_ref=document_name,
                    chapter=chapter,
                )
            )
        elif by_size and produced:
            builder.warnings.append(
                IngestionWarning(
                    code="long_document_split_by_size",
                    message=(
                        f"Cut a {length:,}-character document into {produced} chapters, "
                        f"{by_size} of them by size at about {SIZE_SPLIT_TARGET_CHARS:,} "
                        "characters where no chapter heading was found"
                    ),
                    source_ref=document_name,
                    chapter=first_chapter,
                )
            )
        elif len(segments) > 1:
            builder.warnings.append(
                IngestionWarning(
                    code="spine_document_split",
                    message=(
                        f"Split a {length:,}-character document into {produced} chapters"
                        " at its chapter headings"
                    ),
                    source_ref=document_name,
                    chapter=first_chapter,
                )
            )
        elif length > UNSPLIT_DOCUMENT_CHARS:
            builder.warnings.append(
                IngestionWarning(
                    code="long_document_unsplit",
                    message=(
                        f"A {length:,}-character document stayed one chapter: no chapter"
                        " heading was found to split it at"
                    ),
                    source_ref=document_name,
                    chapter=first_chapter,
                )
            )

    if not builder.blocks:
        raise ValueError("EPUB contains no supported content blocks")

    builder.blocks, notices = fold_heading_only_chapters(builder.blocks)
    builder.warnings.extend(notices)
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
