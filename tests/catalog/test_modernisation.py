import json
import uuid
from types import SimpleNamespace

import pytest

from almonium_book_processor.catalog.models import Chapter, ContentBlock, Edition, Work
from almonium_book_processor.catalog.modernisation import (
    queue_advice,
    ready_to_generate,
    recommended_now,
    run_advice,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def original(settings, monkeypatch):
    settings.OPENAI_API_KEY = "fake"
    settings.OPENAI_TRANSLATION_QUALITY_MODEL = "test-model"
    work = Work.objects.create(slug="modern-work", title="Old Novel", author="Author")
    edition = Edition.objects.create(
        work=work,
        slug="modern-original",
        title="Old Novel",
        author="Author",
        language="en",
        cefr_level="C1",
        source_sha256="a" * 64,
    )
    chapters = []
    for number in (1, 2, 3):
        chapter = Chapter.objects.create(edition=edition, sequence=number)
        ContentBlock.objects.create(
            edition=edition,
            chapter=chapter,
            sequence=1,
            block_id=f"c{number}.p1",
            block_type=ContentBlock.BlockType.PARAGRAPH,
            text=(
                "Before dawn, the traveller departed from the quiet town and crossed "
                "the valley alone."
            ),
            align_group=uuid.uuid4(),
        )
        chapters.append(chapter)
    monkeypatch.setattr(
        "almonium_book_processor.catalog.modernisation.analysis_context",
        lambda _: {
            "projection_state": "complete",
            "chapter_analysis_run": SimpleNamespace(id=uuid.uuid4()),
            "chapter_projections": [
                {
                    "chapter": chapter,
                    "difficulty": {"windows": [{"modernisation_would_help": True}]},
                }
                for chapter in chapters
            ],
        },
    )
    # Keep the saved analysis identity stable across queueing and execution.
    from almonium_book_processor.catalog import modernisation

    context = modernisation.analysis_context(edition)
    monkeypatch.setattr(modernisation, "analysis_context", lambda _: context)
    return edition


class Provider:
    def __init__(self, recommend=False):
        self.recommend = recommend

    def respond(self, body):
        source = json.loads(body["input"])
        block = source["samples"][0]["blocks"][0]
        answer = {
            "recommend_full_edition": self.recommend,
            "confidence": "medium",
            "reasons": ["The obstacle is local and suitable for a gloss."],
            "barriers": [
                {
                    "block_id": block["block_id"],
                    "quote": "Before dawn",
                    "action": "gloss",
                    "reason": "Explain the time expression beside the text.",
                }
            ],
        }
        return {
            "id": "advice-response",
            "status": "completed",
            "usage": {"input_tokens": 100, "output_tokens": 50},
            "output": [
                {
                    "type": "message",
                    "content": [{"type": "output_text", "text": json.dumps(answer)}],
                }
            ],
        }


def test_advice_is_versioned_paid_and_does_not_change_original(original):
    run = queue_advice(original.id, dispatch=False)
    assert queue_advice(original.id, dispatch=False).id == run.id
    run_advice(run.id, provider=Provider())
    run.refresh_from_db()
    assert run.summary["advice"]["recommend_full_edition"] is False
    assert run.ai_runs.get().estimated_cost_usd is not None
    assert not ready_to_generate(original)
    assert original.blocks.count() == 3


def test_advice_requires_current_analysis(original, monkeypatch):
    monkeypatch.setattr(
        "almonium_book_processor.catalog.modernisation.analysis_context",
        lambda _: {"projection_state": "stale"},
    )
    with pytest.raises(ValueError, match="current, complete"):
        queue_advice(original.id, dispatch=False)


def test_positive_advice_expires_when_source_analysis_changes(original, monkeypatch):
    run = queue_advice(original.id, dispatch=False)
    run_advice(run.id, provider=Provider(recommend=True))
    assert recommended_now(original)
    monkeypatch.setattr(
        "almonium_book_processor.catalog.modernisation.analysis_context",
        lambda _: {"projection_state": "stale"},
    )
    assert not recommended_now(original)
