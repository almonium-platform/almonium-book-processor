"""Dispatch supported source files to their format-specific adapter."""

from __future__ import annotations

from pathlib import Path

from almonium_book_processor.ingest.epub import ingest_epub
from almonium_book_processor.ingest.tei import ingest_tei
from almonium_book_processor.models import BookArtifact

SUPPORTED_SOURCE_EXTENSIONS = {".epub", ".xml"}


def source_format(path: str | Path) -> str:
    extension = Path(path).suffix.lower()
    if extension == ".epub":
        return "epub"
    if extension == ".xml":
        return "tei"
    raise ValueError(f"Unsupported source extension: {extension or '(none)'}")


def ingest_source(
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
    adapter = ingest_epub if source_format(path) == "epub" else ingest_tei
    return adapter(
        path,
        edition_slug=edition_slug,
        work_slug=work_slug,
        title=title,
        author=author,
        language=language,
        edition_type=edition_type,
        source_edition_slug=source_edition_slug,
        cefr_level=cefr_level,
        expected_chapters=expected_chapters,
    )
