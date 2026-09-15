from __future__ import annotations

import json
from pathlib import Path

import pytest

from almonium_book_processor.artifact_migrations import migrate_artifact_payload
from almonium_book_processor.models import SCHEMA_VERSION, BookArtifact

# A real schema-1 artifact from the local catalog. data/ is not committed, so this
# regression runs where the catalog is checked out and is skipped in CI.
FRANKENSTEIN_ARTIFACT = (
    Path(__file__).parents[1] / "data" / "normalized-catalog" / "shelley-frankenstein-en-orig.json"
)


@pytest.mark.skipif(
    not FRANKENSTEIN_ARTIFACT.exists(),
    reason="needs the local normalized catalog under data/, which is not committed",
)
def test_schema_one_frankenstein_artifact_migrates_to_current_schema() -> None:
    legacy_payload = json.loads(FRANKENSTEIN_ARTIFACT.read_bytes())

    artifact = BookArtifact.model_validate(migrate_artifact_payload(legacy_payload))

    assert artifact.schema_version == SCHEMA_VERSION
    assert artifact.edition.edition_slug == "shelley-frankenstein-en-orig"
    assert artifact.edition.work_slug == "shelley-frankenstein"
    assert len(artifact.blocks) == 815
    assert all(block.schema_version == SCHEMA_VERSION for block in artifact.blocks)


def test_schema_two_cefr_target_migrates_to_cefr_level() -> None:
    payload = {
        "schema_version": 2,
        "processor_version": "0.1.0",
        "edition": {
            "edition_slug": "shelley-frankenstein-en-a2",
            "work_slug": "shelley-frankenstein",
            "title": "Frankenstein",
            "author": "Mary Shelley",
            "language": "en",
            "edition_type": "adaptation",
            "source_edition_slug": "shelley-frankenstein-en-orig",
            "cefr_target": "A2",
            "source": {
                "format": "legacy_html",
                "path": "books/1.html",
                "sha256": "a" * 64,
            },
        },
        "blocks": [
            {
                "schema_version": 2,
                "edition_slug": "shelley-frankenstein-en-a2",
                "block_id": "c1.p1",
                "chapter": 1,
                "seq": 1,
                "type": "paragraph",
                "text": "A dark November night.",
            }
        ],
    }

    artifact = BookArtifact.model_validate(migrate_artifact_payload(payload))

    assert artifact.edition.cefr_level == "A2"
    assert artifact.blocks[0].schema_version == SCHEMA_VERSION
