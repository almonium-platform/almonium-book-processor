from __future__ import annotations

import json
import uuid
from decimal import Decimal
from types import SimpleNamespace

import pytest

from almonium_book_processor.catalog.ai_alignment import (
    complete_alignment_batch,
    submit_alignment_batch,
)
from almonium_book_processor.catalog.models import (
    AIRun,
    AlignmentGroupReview,
    BlockAlignment,
    Chapter,
    ChapterAlignment,
    ContentBlock,
    Edition,
    Work,
)

pytestmark = pytest.mark.django_db


def aligned_edition() -> tuple[Edition, ContentBlock, ContentBlock]:
    work = Work.objects.create(
        slug="ai-alignment-work",
        title="AI Alignment Work",
        author="Ada Author",
        original_language="en",
    )
    source = Edition.objects.create(
        slug="ai-alignment-work-en",
        work=work,
        title=work.title,
        author=work.author,
        language="en",
        source_sha256="a" * 64,
    )
    target = Edition.objects.create(
        slug="ai-alignment-work-fr",
        work=work,
        source_edition=source,
        title=work.title,
        author=work.author,
        language="fr",
        source_sha256="b" * 64,
        edition_type=Edition.EditionType.HUMAN_TRANSLATION,
    )
    source_chapter = Chapter.objects.create(edition=source, sequence=2)
    target_chapter = Chapter.objects.create(edition=target, sequence=1)
    source_block = ContentBlock.objects.create(
        edition=source,
        chapter=source_chapter,
        block_id="c2.p1",
        sequence=1,
        block_type=ContentBlock.BlockType.PARAGRAPH,
        text="When I was seventeen, I left for Ingolstadt.",
    )
    target_block = ContentBlock.objects.create(
        edition=target,
        chapter=target_chapter,
        block_id="c1.p1",
        sequence=1,
        block_type=ContentBlock.BlockType.PARAGRAPH,
        text="À dix-sept ans, je partis pour Ingolstadt.",
    )
    group_id = uuid.uuid4()
    ChapterAlignment.objects.create(
        source_edition=source,
        target_edition=target,
        source_chapter=source_chapter,
        target_chapter=target_chapter,
        group_id=group_id,
        confidence=0.8,
        strategy="test",
    )
    BlockAlignment.objects.create(
        source_edition=source,
        target_edition=target,
        source_block=source_block,
        target_block=target_block,
        confidence=0.7,
        strategy="local-test",
    )
    return target, source_block, target_block


def test_submit_and_complete_alignment_batch(monkeypatch) -> None:
    target, source_block, target_block = aligned_edition()
    submitted = {}

    def fake_submit(self, requests, *, metadata):
        submitted["requests"] = list(requests)
        submitted["metadata"] = metadata
        return SimpleNamespace(id="batch_test", status="validating", input_file_id="file_test")

    monkeypatch.setattr(
        "almonium_book_processor.catalog.ai_alignment.OpenAIBatchProvider.submit",
        fake_submit,
    )
    monkeypatch.setattr(
        "almonium_book_processor.ai.openai_provider.OpenAIBatchProvider.__init__",
        lambda self: None,
    )

    ai_run = submit_alignment_batch(str(target.id))

    assert ai_run.status == AIRun.Status.SUBMITTED
    assert ai_run.provider_request_id == "batch_test"
    assert len(submitted["requests"]) == 1
    assert submitted["requests"][0]["url"] == "/v1/responses"
    assert "When I was seventeen" in submitted["requests"][0]["body"]["input"]
    assert "When I was seventeen" not in json.dumps(ai_run.request_payload)

    custom_id = submitted["requests"][0]["custom_id"]
    decision = {
        "same_text": True,
        "confidence": 0.97,
        "alignments": [
            {
                "source_block_ids": [str(source_block.id)],
                "target_block_ids": [str(target_block.id)],
                "relation": "1:1",
                "confidence": 0.96,
                "evidence": "Both passages describe leaving for Ingolstadt at seventeen.",
            }
        ],
        "unmatched_source_block_ids": [],
        "unmatched_target_block_ids": [],
        "needs_human_review": False,
        "notes": "Direct translation.",
    }
    output_lines = [
        {
            "custom_id": custom_id,
            "response": {
                "status_code": 200,
                "body": {
                    "output": [
                        {
                            "type": "message",
                            "content": [{"type": "output_text", "text": json.dumps(decision)}],
                        }
                    ],
                    "usage": {
                        "input_tokens": 100,
                        "output_tokens": 20,
                        "input_tokens_details": {"cached_tokens": 0},
                        "output_tokens_details": {"reasoning_tokens": 5},
                    },
                },
            },
        }
    ]

    uncertain = complete_alignment_batch(ai_run, output_lines)

    ai_run.refresh_from_db()
    alignment = BlockAlignment.objects.get(target_edition=target)
    review = AlignmentGroupReview.objects.get(target_edition=target)
    assert uncertain == []
    assert ai_run.status == AIRun.Status.SUCCEEDED
    assert ai_run.estimated_cost_usd == Decimal("0.000022")
    assert alignment.strategy == "openai-gpt-5.6-luna-structured-v1"
    assert review.decision == AlignmentGroupReview.Decision.AI_ACCEPTED


def test_invalid_primary_output_is_escalated_without_failing_batch(monkeypatch) -> None:
    target, source_block, target_block = aligned_edition()

    def fake_submit(self, requests, *, metadata):
        return SimpleNamespace(
            id="batch_invalid", status="validating", input_file_id="file_invalid"
        )

    monkeypatch.setattr(
        "almonium_book_processor.catalog.ai_alignment.OpenAIBatchProvider.submit",
        fake_submit,
    )
    monkeypatch.setattr(
        "almonium_book_processor.ai.openai_provider.OpenAIBatchProvider.__init__",
        lambda self: None,
    )
    ai_run = submit_alignment_batch(str(target.id))
    custom_id = next(iter(ai_run.request_payload["manifest"]))
    duplicate_decision = {
        "same_text": True,
        "confidence": 0.95,
        "alignments": [
            {
                "source_block_ids": [str(source_block.id)],
                "target_block_ids": [str(target_block.id)],
                "relation": "1:1",
                "confidence": 0.95,
                "evidence": "First duplicate.",
            },
            {
                "source_block_ids": [str(source_block.id)],
                "target_block_ids": [str(target_block.id)],
                "relation": "1:1",
                "confidence": 0.95,
                "evidence": "Second duplicate.",
            },
        ],
        "unmatched_source_block_ids": [],
        "unmatched_target_block_ids": [],
        "needs_human_review": False,
        "notes": "Invalid duplicate output.",
    }
    output_lines = [
        {
            "custom_id": custom_id,
            "response": {
                "status_code": 200,
                "body": {
                    "output": [
                        {
                            "type": "message",
                            "content": [
                                {"type": "output_text", "text": json.dumps(duplicate_decision)}
                            ],
                        }
                    ],
                    "usage": {"input_tokens": 50, "output_tokens": 10},
                },
            },
        }
    ]

    uncertain = complete_alignment_batch(ai_run, output_lines)

    ai_run.refresh_from_db()
    assert uncertain == [ai_run.request_payload["manifest"][custom_id]["chapter_group_id"]]
    assert ai_run.status == AIRun.Status.SUCCEEDED
    assert custom_id in ai_run.response_payload["invalid_outputs"]
    assert ai_run.input_tokens == 50
