"""Almonium's offline ebook ingestion and normalisation pipeline."""

__version__ = "0.2.0"

from almonium_book_processor.config.celery import app as celery_app
from almonium_book_processor.models import (
    SCHEMA_VERSION,
    BlockType,
    BookArtifact,
    ContentBlock,
    EditionMetadata,
    IngestionWarning,
    SentenceSpan,
    SourceMetadata,
)

__all__ = [
    "SCHEMA_VERSION",
    "BlockType",
    "BookArtifact",
    "celery_app",
    "ContentBlock",
    "EditionMetadata",
    "IngestionWarning",
    "SentenceSpan",
    "SourceMetadata",
]


def ingest_processor_version() -> str:
    """The package version and the cut that made an edition, as its ingest run records it."""

    from almonium_book_processor.ingest.common import INGEST_VERSION

    return f"{__version__}+{INGEST_VERSION}"
