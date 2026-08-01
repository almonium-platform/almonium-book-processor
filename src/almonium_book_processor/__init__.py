"""Almonium's offline ebook ingestion and normalisation pipeline."""

__version__ = "0.1.0"

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
