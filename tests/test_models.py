from __future__ import annotations

import pytest
from pydantic import ValidationError

from almonium_book_processor.models import (
    BlockType,
    BookArtifact,
    ContentBlock,
    EditionMetadata,
    SourceMetadata,
)


def edition() -> EditionMetadata:
    return EditionMetadata(
        edition_slug="kafka-verwandlung-de-orig",
        work_slug="kafka-verwandlung",
        title="Die Verwandlung",
        author="Franz Kafka",
        language="de",
        source=SourceMetadata(format="epub", path="book.epub", sha256="a" * 64),
    )


def test_artifact_rejects_non_contiguous_chapter_sequence() -> None:
    with pytest.raises(ValidationError, match="sequence must be contiguous"):
        BookArtifact(
            processor_version="0.1.0",
            edition=edition(),
            blocks=[
                ContentBlock(
                    edition_slug=edition().edition_slug,
                    block_id="c1.p2",
                    chapter=1,
                    seq=2,
                    type=BlockType.PARAGRAPH,
                    text="Text",
                )
            ],
        )


def test_machine_derived_edition_requires_lineage() -> None:
    with pytest.raises(ValidationError, match="require source_edition_slug"):
        EditionMetadata(
            edition_slug="kafka-verwandlung-uk-machine",
            work_slug="kafka-verwandlung",
            title="Перевтілення",
            author="Франц Кафка",
            language="uk",
            edition_type="machine_translation",
            source=SourceMetadata(format="epub", path="book.epub", sha256="b" * 64),
        )


def test_edition_rejects_unknown_language_code() -> None:
    with pytest.raises(ValidationError):
        EditionMetadata(
            edition_slug="spanish-novel",
            work_slug="spanish-novel",
            title="A Spanish Novel",
            author="Ada Author",
            language="zz",
            source=SourceMetadata(format="tei", path="book.xml", sha256="c" * 64),
        )
