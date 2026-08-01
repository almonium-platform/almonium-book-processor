"""Source adapters for normalized book artifacts."""

from almonium_book_processor.ingest.epub import ingest_epub
from almonium_book_processor.ingest.source import ingest_source
from almonium_book_processor.ingest.tei import ingest_tei

__all__ = ["ingest_epub", "ingest_source", "ingest_tei"]
