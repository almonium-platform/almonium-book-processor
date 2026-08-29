from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from almonium_book_processor.catalog.models import (
    Chapter,
    ContentBlock,
    Edition,
    EditionArtifact,
    PipelineRun,
    Work,
)
from almonium_book_processor.catalog.tasks import (
    analyze_edition_lexicon,
    process_normalized_edition,
)

pytestmark = pytest.mark.django_db


def _edition() -> Edition:
    work = Work.objects.create(
        slug="lexical-work",
        title="Lexical Work",
        author="Ada Author",
        original_language="en",
    )
    edition = Edition.objects.create(
        slug="lexical-work-en-original",
        work=work,
        title=work.title,
        author=work.author,
        language="en",
        edition_type=Edition.EditionType.ORIGINAL,
        source_sha256="a" * 64,
    )
    chapter = Chapter.objects.create(edition=edition, sequence=1)
    ContentBlock.objects.create(
        edition=edition,
        chapter=chapter,
        block_id="c1.p1",
        sequence=1,
        block_type=ContentBlock.BlockType.PARAGRAPH,
        text="Lantern lantern harbor.",
    )
    return edition


def test_lexical_task_persists_two_versioned_artifacts_idempotently(monkeypatch) -> None:
    edition = _edition()
    monkeypatch.setattr(
        "almonium_book_processor.catalog.tasks.lexical_runtime_signature",
        lambda language: {"wordfreq_version": "test"},
    )
    monkeypatch.setattr(
        "almonium_book_processor.catalog.tasks.analyze_lexicon",
        lambda blocks, language: (
            {
                "schema_version": 1,
                "language": language,
                "total_tokens": 3,
                "distinct_lemmas": 2,
                "type_token_ratio": 0.666667,
                "frequency_bands": {"uncommon": 3},
                "selection_policy": "lexical-v1",
            },
            {
                "schema_version": 1,
                "language": language,
                "title": "50 useful words from this book",
                "selection_policy": "lexical-v1",
                "requested_limit": 50,
                "words": [{"lemma": "lantern", "display": "Lantern"}],
            },
        ),
    )

    analyze_edition_lexicon.run(str(edition.id))
    analyze_edition_lexicon.run(str(edition.id))

    assert edition.artifacts.count() == 2
    assert set(edition.artifacts.values_list("kind", flat=True)) == {
        EditionArtifact.Kind.LEXICAL_PROFILE,
        EditionArtifact.Kind.USEFUL_WORDS,
    }
    run = edition.pipeline_runs.get(stage=PipelineRun.Stage.LEXICAL)
    assert run.status == PipelineRun.Status.SUCCEEDED
    assert run.summary["useful_words"] == 1


def test_lexical_task_creates_new_artifact_versions_after_text_changes(monkeypatch) -> None:
    edition = _edition()
    monkeypatch.setattr(
        "almonium_book_processor.catalog.tasks.lexical_runtime_signature",
        lambda language: {"wordfreq_version": "test"},
    )
    monkeypatch.setattr(
        "almonium_book_processor.catalog.tasks.analyze_lexicon",
        lambda blocks, language: (
            {
                "schema_version": 1,
                "language": language,
                "total_tokens": 3,
                "distinct_lemmas": 2,
                "type_token_ratio": 0.666667,
                "frequency_bands": {},
                "selection_policy": "lexical-v1",
            },
            {
                "schema_version": 1,
                "language": language,
                "title": "50 useful words from this book",
                "selection_policy": "lexical-v1",
                "requested_limit": 50,
                "words": [],
            },
        ),
    )
    analyze_edition_lexicon.run(str(edition.id))

    block = edition.blocks.get()
    block.text = "Lantern lantern voyage."
    block.save(update_fields=["text", "updated_at"])
    analyze_edition_lexicon.run(str(edition.id))

    assert edition.artifacts.count() == 4
    assert edition.pipeline_runs.filter(stage=PipelineRun.Stage.LEXICAL).count() == 2


def test_standalone_original_becomes_ready_and_queues_enrichment(monkeypatch) -> None:
    edition = _edition()
    queued = []
    monkeypatch.setattr(
        "almonium_book_processor.catalog.tasks.split_sentences",
        lambda text, language: [text],
    )
    monkeypatch.setattr(
        "almonium_book_processor.catalog.tasks.analyze_edition_lexicon.delay",
        lambda edition_id: queued.append(("lexical", edition_id)),
    )
    monkeypatch.setattr(
        "almonium_book_processor.catalog.tasks.analyze_edition_source_quality.delay",
        lambda edition_id: queued.append(("source_qa", edition_id)),
    )

    process_normalized_edition.run(str(edition.id))

    edition.refresh_from_db()
    assert edition.status == Edition.Status.READY
    assert queued == [("lexical", str(edition.id)), ("source_qa", str(edition.id))]


def test_lexical_queue_failure_does_not_block_standalone_original(monkeypatch) -> None:
    edition = _edition()
    queued = []
    monkeypatch.setattr(
        "almonium_book_processor.catalog.tasks.split_sentences",
        lambda text, language: [text],
    )

    def fail_to_queue(edition_id: str) -> None:
        raise RuntimeError("broker unavailable")

    monkeypatch.setattr(
        "almonium_book_processor.catalog.tasks.analyze_edition_lexicon.delay",
        fail_to_queue,
    )
    monkeypatch.setattr(
        "almonium_book_processor.catalog.tasks.analyze_edition_source_quality.delay",
        queued.append,
    )

    process_normalized_edition.run(str(edition.id))

    edition.refresh_from_db()
    assert edition.status == Edition.Status.READY
    assert queued == [str(edition.id)]


def test_edition_page_displays_useful_words_artifact(client) -> None:
    edition = _edition()
    user = get_user_model().objects.create_superuser(
        username="lexical-editor",
        email="lexical@example.test",
        password="password",
    )
    client.force_login(user)
    profile = EditionArtifact.objects.create(
        edition=edition,
        kind=EditionArtifact.Kind.LEXICAL_PROFILE,
        input_hash="b" * 64,
        processor_version="lexical-v1",
        payload={"total_tokens": 3, "distinct_lemmas": 2},
    )
    EditionArtifact.objects.create(
        edition=edition,
        kind=EditionArtifact.Kind.USEFUL_WORDS,
        input_hash=profile.input_hash,
        processor_version=profile.processor_version,
        payload={
            "words": [
                {
                    "display": "lantern",
                    "count": 2,
                    "chapter_count": 1,
                    "frequency_band": "uncommon",
                    "occurrences": [{"context": "The lantern burned."}],
                }
            ]
        },
    )

    response = client.get(reverse("catalog:edition-detail", args=[edition.id]))

    assert response.status_code == 200
    assert "50 useful words from this book" in response.content.decode()
    assert "The lantern burned." in response.content.decode()
