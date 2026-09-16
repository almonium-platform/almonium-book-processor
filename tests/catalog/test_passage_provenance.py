import hashlib

import pytest

from almonium_book_processor.catalog.models import ContentBlockRevision
from almonium_book_processor.catalog.passage_provenance import passage_provenance
from tests.catalog.test_sentence_alignment import pair  # noqa: F401

pytestmark = pytest.mark.django_db


def test_missing_generation_is_explicit_and_revision_is_separate(pair):  # noqa: F811
    edition, _ = pair
    block = edition.blocks.get()
    block.attributes = {"translation": {"model": "recorded-model"}}
    block.save()
    revision = ContentBlockRevision.objects.create(
        edition=edition,
        block=block,
        stable_block_id=block.block_id,
        previous_text="O n returning.",
        revised_text=block.text,
        notes="Joined drop cap.",
    )
    result = passage_provenance([block])[(edition.id, block.block_id)]
    assert result["model"] == "recorded-model"
    assert result["generation_run"] == "Not linked to this passage"
    assert result["prompt"] == "Not recorded for this passage"
    assert result["latest_text_revision"] == str(revision.id)
    assert result["text_sha256"] == hashlib.sha256(block.text.encode()).hexdigest()
