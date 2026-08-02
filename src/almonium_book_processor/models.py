"""Versioned domain models shared by pipeline stages.

The normalized artifact is deliberately presentation-free. Reader concerns such
as drop caps and first-paragraph styling do not belong in these models.
"""

from __future__ import annotations

import re
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

SCHEMA_VERSION = 3


class StrictModel(BaseModel):
    """Forbid accidental schema growth and keep serialized output stable."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class BlockType(StrEnum):
    PARAGRAPH = "paragraph"
    HEADING = "heading"
    VERSE_LINE = "verse_line"
    VERSE_STANZA = "verse_stanza"
    BLOCKQUOTE = "blockquote"
    LETTER = "letter"
    EPIGRAPH = "epigraph"
    DIALOGUE = "dialogue"
    FOOTNOTE = "footnote"
    IMAGE = "image"
    SEPARATOR = "separator"


class SentenceSpan(StrictModel):
    """Character offsets into a block's normalized text.

    Sentence splitting is build-order step 2, so ingestion initializes this list
    as empty while reserving the stable contract now.
    """

    id: str = Field(min_length=1)
    start: int = Field(ge=0)
    end: int = Field(gt=0)

    @model_validator(mode="after")
    def end_follows_start(self) -> SentenceSpan:
        if self.end <= self.start:
            raise ValueError("sentence end must be greater than start")
        return self


class SourceMetadata(StrictModel):
    format: Literal["epub", "tei", "legacy_html"]
    path: str = Field(min_length=1)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    identifier: str | None = None


class EditionMetadata(StrictModel):
    edition_slug: str = Field(min_length=1, max_length=160)
    work_slug: str = Field(min_length=1, max_length=160)
    title: str = Field(min_length=1)
    author: str = Field(min_length=1)
    language: str = Field(min_length=2, max_length=35)
    edition_type: Literal[
        "original", "human_translation", "machine_translation", "adaptation", "abridgement"
    ] = "original"
    source_edition_slug: str | None = None
    cefr_level: Literal["A1", "A2", "B1", "B2", "C1", "C2"] | None = None
    source: SourceMetadata

    @model_validator(mode="after")
    def validate_identifiers_and_lineage(self) -> EditionMetadata:
        slug_pattern = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
        if not slug_pattern.fullmatch(self.edition_slug):
            raise ValueError("edition_slug must be a lowercase kebab-case identifier")
        if not slug_pattern.fullmatch(self.work_slug):
            raise ValueError("work_slug must be a lowercase kebab-case identifier")
        if (
            self.edition_type in {"adaptation", "abridgement", "machine_translation"}
            and not self.source_edition_slug
        ):
            raise ValueError(f"{self.edition_type} editions require source_edition_slug")
        if self.edition_type == "adaptation" and not self.cefr_level:
            raise ValueError("adaptation editions require cefr_level")
        return self


class ContentBlock(StrictModel):
    schema_version: Literal[3] = SCHEMA_VERSION
    edition_slug: str
    block_id: str = Field(pattern=r"^c\d+\.[a-z]+\d+$")
    chapter: int = Field(ge=0)
    seq: int = Field(ge=1)
    type: BlockType
    text: str = ""
    sentences: list[SentenceSpan] = Field(default_factory=list)
    align_group: int | None = Field(default=None, ge=1)
    source_ref: str | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_content(self) -> ContentBlock:
        if self.type not in {BlockType.IMAGE, BlockType.SEPARATOR} and not self.text:
            raise ValueError(f"{self.type} blocks require text")
        if self.type == BlockType.IMAGE and not self.source_ref:
            raise ValueError("image blocks require source_ref")
        for sentence in self.sentences:
            if sentence.end > len(self.text):
                raise ValueError(f"sentence {sentence.id} ends outside block text")
        return self


class IngestionWarning(StrictModel):
    code: str = Field(min_length=1)
    message: str = Field(min_length=1)
    source_ref: str | None = None
    chapter: int | None = Field(default=None, ge=0)


class IngestionWarningCode(StrEnum):
    """Known notices emitted by the EPUB and TEI importers.

    ``IngestionWarning.code`` deliberately remains a string so old normalized
    artifacts and newer processors can still be imported. This enum is the
    catalogue maintained by this application for warnings it emits itself.
    """

    EMPTY_BLOCK_SKIPPED = "empty_block_skipped"
    IMAGE_WITHOUT_SOURCE = "image_without_source"
    EMPTY_SPINE_DOCUMENT = "empty_spine_document"
    EMPTY_TEI_SECTION = "empty_tei_section"
    UNEXPECTED_CHAPTER_COUNT = "unexpected_chapter_count"


class IngestionWarningSeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


INGESTION_WARNING_SEVERITIES: dict[str, IngestionWarningSeverity] = {
    IngestionWarningCode.EMPTY_BLOCK_SKIPPED: IngestionWarningSeverity.INFO,
    IngestionWarningCode.IMAGE_WITHOUT_SOURCE: IngestionWarningSeverity.WARNING,
    IngestionWarningCode.EMPTY_SPINE_DOCUMENT: IngestionWarningSeverity.WARNING,
    IngestionWarningCode.EMPTY_TEI_SECTION: IngestionWarningSeverity.WARNING,
    IngestionWarningCode.UNEXPECTED_CHAPTER_COUNT: IngestionWarningSeverity.WARNING,
}


def ingestion_warning_severity(code: str) -> IngestionWarningSeverity:
    """Return a conservative severity for an importer warning code.

    Unknown codes require review: silently treating a new processor warning as
    informational could hide a lost part of a book.
    """

    return INGESTION_WARNING_SEVERITIES.get(code, IngestionWarningSeverity.WARNING)


class BookArtifact(StrictModel):
    schema_version: Literal[3] = SCHEMA_VERSION
    processor_version: str = Field(min_length=1)
    edition: EditionMetadata
    blocks: list[ContentBlock]
    warnings: list[IngestionWarning] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_blocks(self) -> BookArtifact:
        seen_ids: set[str] = set()
        expected_seq: dict[int, int] = {}
        for block in self.blocks:
            if block.edition_slug != self.edition.edition_slug:
                raise ValueError(f"block {block.block_id} belongs to another edition")
            if block.block_id in seen_ids:
                raise ValueError(f"duplicate block_id: {block.block_id}")
            seen_ids.add(block.block_id)

            expected = expected_seq.get(block.chapter, 1)
            if block.seq != expected:
                raise ValueError(
                    f"chapter {block.chapter} block sequence must be contiguous; "
                    f"expected {expected}, got {block.seq}"
                )
            expected_seq[block.chapter] = expected + 1
        return self
