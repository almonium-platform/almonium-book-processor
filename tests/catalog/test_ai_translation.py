from __future__ import annotations

import json
import uuid
from types import SimpleNamespace

import pytest

from almonium_book_processor.catalog.ai_translation import (
    complete_translation_batch,
    create_parallel_translation,
    submit_translation_batch,
)
from almonium_book_processor.catalog.models import (
    AIRun,
    Chapter,
    ContentBlock,
    Edition,
    QAWarning,
    Work,
)

pytestmark = pytest.mark.django_db


def canonical_edition() -> Edition:
    work = Work.objects.create(
        slug="translation-work",
        title="Translation Work",
        author="Ada Author",
        original_language="en",
        publication_year=1818,
    )
    edition = Edition.objects.create(
        slug="translation-work-en",
        work=work,
        title=work.title,
        author=work.author,
        language="en",
        source_sha256="a" * 64,
        parallel_role=Edition.ParallelRole.CANONICAL,
    )
    chapter = Chapter.objects.create(edition=edition, sequence=1, title="Chapter I")
    ContentBlock.objects.create(
        edition=edition,
        chapter=chapter,
        block_id="c1.h1",
        sequence=1,
        block_type=ContentBlock.BlockType.HEADING,
        text="Chapter I",
        align_group=uuid.uuid4(),
    )
    ContentBlock.objects.create(
        edition=edition,
        chapter=chapter,
        block_id="c1.p2",
        sequence=2,
        block_type=ContentBlock.BlockType.PARAGRAPH,
        text="It was on a dreary night of November that I beheld the accomplishment of my toils.",
        align_group=uuid.uuid4(),
    )
    return edition


def fake_provider(monkeypatch, sink: dict) -> None:
    def fake_submit(self, requests, *, metadata):
        sink["requests"] = list(requests)
        sink["metadata"] = metadata
        return SimpleNamespace(id="batch_tr", status="validating", input_file_id="file_tr")

    monkeypatch.setattr(
        "almonium_book_processor.catalog.ai_translation.OpenAIBatchProvider.submit",
        fake_submit,
    )
    monkeypatch.setattr(
        "almonium_book_processor.ai.openai_provider.OpenAIBatchProvider.__init__",
        lambda self: None,
    )


def output_line(custom_id: str, blocks: list[dict]) -> dict:
    return {
        "custom_id": custom_id,
        "response": {
            "status_code": 200,
            "body": {
                "output": [
                    {
                        "type": "message",
                        "content": [
                            {
                                "type": "output_text",
                                "text": json.dumps({"blocks": blocks}, ensure_ascii=False),
                            }
                        ],
                    }
                ],
                "usage": {
                    "input_tokens": 900,
                    "output_tokens": 1100,
                    "input_tokens_details": {"cached_tokens": 0},
                    "output_tokens_details": {"reasoning_tokens": 40},
                },
            },
        },
    }


def translated(block_id: str, text: str, **overrides) -> dict:
    return {
        "block_id": block_id,
        "text": text,
        "sentence_count_changed": False,
        "confidence": 0.95,
        "note": "",
        **overrides,
    }


def test_parallel_translation_inherits_canonical_block_groups(monkeypatch) -> None:
    source = canonical_edition()
    edition = create_parallel_translation(
        source_edition=source,
        target_language="fr",
        register="period-faithful",
        tier="quality",
    )
    assert edition.parallel_role == Edition.ParallelRole.PARALLEL
    assert edition.supports_parallel_reading is True

    sink: dict = {}
    fake_provider(monkeypatch, sink)
    ai_run = submit_translation_batch(str(edition.id), tier="quality")

    assert ai_run.status == AIRun.Status.SUBMITTED
    assert len(sink["requests"]) == 1
    body = sink["requests"][0]["body"]
    assert "dreary night of November" in body["input"]
    # The register and work metadata must reach the model, not just the blocks.
    assert "period-faithful" in body["instructions"]
    assert "published 1818" in body["instructions"]

    custom_id = sink["requests"][0]["custom_id"]
    complete_translation_batch(
        ai_run,
        [
            output_line(
                custom_id,
                [
                    translated("c1.h1", "Chapitre premier"),
                    translated(
                        "c1.p2",
                        "Ce fut par une lugubre nuit de novembre que je contemplai "
                        "l'accomplissement de mes travaux.",
                    ),
                ],
            )
        ],
    )

    edition.refresh_from_db()
    assert edition.status == Edition.Status.READY
    blocks = {block.block_id: block for block in edition.blocks.all()}
    assert set(blocks) == {"c1.h1", "c1.p2"}
    # This is the whole architecture: alignment by construction.
    for block_id, block in blocks.items():
        assert block.align_group == source.blocks.get(block_id=block_id).align_group
    assert edition.chapters.get(sequence=1).title == "Chapitre premier"
    assert blocks["c1.p2"].attributes["translation"]["confidence"] == 0.95


def test_missing_block_fails_the_run_without_materializing(monkeypatch) -> None:
    source = canonical_edition()
    edition = create_parallel_translation(
        source_edition=source,
        target_language="fr",
        register="period-faithful",
        tier="quality",
    )
    sink: dict = {}
    fake_provider(monkeypatch, sink)
    ai_run = submit_translation_batch(str(edition.id), tier="quality")
    custom_id = sink["requests"][0]["custom_id"]

    with pytest.raises(ValueError):
        complete_translation_batch(
            ai_run,
            [output_line(custom_id, [translated("c1.h1", "Chapitre premier")])],
        )

    edition.refresh_from_db()
    assert edition.status == Edition.Status.FAILED
    assert edition.blocks.count() == 0


def test_length_and_confidence_gates_send_edition_to_review(monkeypatch) -> None:
    source = canonical_edition()
    edition = create_parallel_translation(
        source_edition=source,
        target_language="fr",
        register="period-faithful",
        tier="quality",
    )
    sink: dict = {}
    fake_provider(monkeypatch, sink)
    ai_run = submit_translation_batch(str(edition.id), tier="quality")
    custom_id = sink["requests"][0]["custom_id"]

    complete_translation_batch(
        ai_run,
        [
            output_line(
                custom_id,
                [
                    translated("c1.h1", "I"),
                    translated("c1.p2", "Nuit.", confidence=0.4),
                ],
            )
        ],
    )

    edition.refresh_from_db()
    assert edition.status == Edition.Status.REVIEW
    codes = set(edition.warnings.values_list("code", flat=True))
    assert "translation_length_ratio" in codes
    assert "translation_low_confidence" in codes
    assert edition.warnings.filter(
        code="translation_low_confidence", severity=QAWarning.Severity.WARNING
    ).exists()


def test_translation_requires_a_canonical_source() -> None:
    source = canonical_edition()
    standalone = Edition.objects.create(
        slug="translation-work-fr-human",
        work=source.work,
        source_edition=source,
        title=source.work.title,
        author=source.author,
        language="fr",
        edition_type=Edition.EditionType.HUMAN_TRANSLATION,
        parallel_role=Edition.ParallelRole.STANDALONE,
    )
    with pytest.raises(ValueError):
        create_parallel_translation(
            source_edition=standalone,
            target_language="de",
            register="period-faithful",
            tier="quality",
        )
    with pytest.raises(ValueError):
        create_parallel_translation(
            source_edition=source,
            target_language="en",
            register="period-faithful",
            tier="quality",
        )


def test_failed_parallel_edition_is_retried_by_resubmitting_translation(
    client, monkeypatch
) -> None:
    from django.contrib.auth import get_user_model
    from django.urls import reverse

    source = canonical_edition()
    edition = create_parallel_translation(
        source_edition=source,
        target_language="uk",
        register="period-faithful",
        tier="draft",
    )
    sink: dict = {}
    fake_provider(monkeypatch, sink)
    submit_translation_batch(str(edition.id), tier="draft")
    # The Batch service rejected the input file, as it did in production.
    Edition.objects.filter(id=edition.id).update(status=Edition.Status.FAILED)

    user = get_user_model().objects.create_superuser(
        username="translation-retry-editor",
        email="translation-retry@example.test",
        password="password",
    )
    client.force_login(user)
    queued = []
    monkeypatch.setattr(
        "almonium_book_processor.catalog.tasks.prepare_translation.delay",
        lambda edition_id, tier="quality": queued.append((edition_id, tier)),
    )

    response = client.post(reverse("catalog:retry-edition", args=[edition.id]))

    assert response.status_code == 302
    # It must reuse the tier of the failed attempt, not silently upgrade to quality.
    assert queued == [(str(edition.id), "draft")]
    edition.refresh_from_db()
    assert edition.status == Edition.Status.PROCESSING


def test_interrupted_direct_run_can_restart(monkeypatch) -> None:
    from almonium_book_processor.catalog.ai_translation import _prepare_translation_run

    source = canonical_edition()
    edition = create_parallel_translation(
        source_edition=source,
        target_language="uk",
        register="period-faithful",
        tier="quality",
    )
    sink: dict = {}
    fake_provider(monkeypatch, sink)
    ai_run = submit_translation_batch(str(edition.id), tier="quality")

    # A batch genuinely in flight must not be resubmitted.
    assert isinstance(_prepare_translation_run(str(edition.id), tier="quality"), AIRun)

    # The same run left "submitted" by a crashed direct worker must restart.
    ai_run.request_payload = {**ai_run.request_payload, "execution": "direct"}
    ai_run.save(update_fields=["request_payload"])
    prepared = _prepare_translation_run(str(edition.id), tier="quality")
    assert isinstance(prepared, tuple)
    assert len(prepared[1]) == 1
