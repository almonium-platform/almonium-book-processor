"""A parallel translation is named and described in its own language, from its source."""

from __future__ import annotations

import json
import uuid

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from almonium_book_processor.catalog.chapter_analysis import (
    _hash,
    analysis_spec,
    current_chapter_hashes,
)
from almonium_book_processor.catalog.chapter_projections import (
    DIFFICULTY_VERSION,
    SUMMARY_VERSION,
)
from almonium_book_processor.catalog.metadata_translation import (
    queue_for_translations_of,
    queue_metadata_translation,
    run_metadata_translation,
    title_page_current,
)
from almonium_book_processor.catalog.models import (
    AIRun,
    Chapter,
    ContentBlock,
    Edition,
    EditionArtifact,
    PipelineRun,
    Work,
)
from almonium_book_processor.catalog.public_chapters import public_chapters
from almonium_book_processor.catalog.tasks import publication_blocker

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def configured(settings, monkeypatch):
    settings.OPENAI_API_KEY = "fake"
    settings.OPENAI_TRANSLATION_QUALITY_MODEL = "test-model"
    monkeypatch.setattr(
        "almonium_book_processor.catalog.tasks.translate_edition_metadata.delay", lambda _: None
    )


def _chapters(edition, groups):
    for sequence, (title, text) in enumerate(
        (("Letter I", "I am by birth a Genevese."), ("Letter II", "How slowly the time passes.")),
        start=1,
    ):
        chapter = Chapter.objects.create(edition=edition, sequence=sequence, title=title)
        ContentBlock.objects.create(
            edition=edition,
            chapter=chapter,
            sequence=1,
            block_id=f"c{sequence}.p1",
            text=text,
            align_group=groups[sequence],
        )


@pytest.fixture
def source():
    work = Work.objects.create(
        slug="frankenstein",
        title="Frankenstein; or, the Modern Prometheus",
        author="Mary Shelley",
        description="A young scientist creates a living being and abandons it.",
        original_language="en",
        publication_year=1818,
    )
    edition = Edition.objects.create(
        work=work,
        slug="frankenstein-en",
        title=work.title,
        author=work.author,
        language="en",
        cefr_level="C1",
        source_sha256="a" * 64,
        status=Edition.Status.PUBLISHED,
        parallel_role=Edition.ParallelRole.CANONICAL,
    )
    _chapters(edition, {1: uuid.uuid4(), 2: uuid.uuid4()})
    return edition


def analysed(source, sequence, descriptions, level="C1"):
    """A complete, current analysis of one source chapter, as the projections store it."""

    chapter = source.chapters.get(sequence=sequence)
    common = {
        "chapter_id": str(chapter.id),
        "chapter_hash": current_chapter_hashes(source)[str(chapter.id)],
        "analysis_spec_hash": _hash(analysis_spec()),
        "complete": True,
    }
    EditionArtifact.objects.create(
        edition=source,
        chapter=chapter,
        kind=EditionArtifact.Kind.DIFFICULTY,
        input_hash=_hash(["difficulty", sequence, descriptions]),
        processor_version=DIFFICULTY_VERSION,
        payload={**common, "cefr_estimate": level},
    )
    EditionArtifact.objects.create(
        edition=source,
        chapter=chapter,
        kind=EditionArtifact.Kind.CHAPTER_SUMMARY,
        input_hash=_hash(["summary", sequence, descriptions]),
        processor_version=SUMMARY_VERSION,
        payload={
            **common,
            "sections": [{"spoiler_free_description": text} for text in descriptions],
        },
    )


@pytest.fixture
def ukrainian(source):
    groups = {
        block.chapter.sequence: block.align_group
        for block in source.blocks.select_related("chapter")
    }
    edition = Edition.objects.create(
        work=source.work,
        slug="frankenstein-uk",
        source_edition=source,
        title=source.title,
        author=source.author,
        language="uk",
        cefr_level="C1",
        edition_type=Edition.EditionType.MACHINE_TRANSLATION,
        parallel_role=Edition.ParallelRole.PARALLEL,
        source_sha256="b" * 64,
        status=Edition.Status.READY,
    )
    _chapters(edition, groups)
    return edition


class Flaky(Exception):
    """An HTTP error as the OpenAI client raises it: a status, no body."""

    status_code = 404


class Provider:
    """Answers each request from its schema name; counts what it was asked."""

    def __init__(self, *, fail_chapter=None, flaky_calls=0):
        self.calls = []
        self.fail_chapter = fail_chapter
        self.flaky_calls = flaky_calls

    def respond(self, body):
        name = body["text"]["format"]["name"]
        self.calls.append(name)
        if self.flaky_calls:
            self.flaky_calls -= 1
            raise Flaky("Error code: 404")
        if name == "title_page":
            assert "Title: Frankenstein; or, the Modern Prometheus" in body["input"]
            assert "A young scientist creates" in body["input"]
            assert "into Ukrainian" in body["instructions"]
            result = {
                "title": "Франкенштейн, або Сучасний Прометей",
                "author": "Мері Шеллі",
                "description": "Молодий науковець створює живу істоту й покидає її.",
                "note": "",
            }
        else:
            descriptions = json.loads(body["input"].split("DESCRIPTIONS\n", 1)[1])
            if self.fail_chapter and f"Chapter {self.fail_chapter}" in body["input"]:
                raise RuntimeError("provider down")
            result = {"descriptions": [f"UK: {text}" for text in descriptions]}
        return {
            "id": f"resp_{len(self.calls)}",
            "status": "completed",
            "usage": {"input_tokens": 100, "output_tokens": 50},
            "output": [
                {
                    "type": "message",
                    "content": [{"type": "output_text", "text": json.dumps(result)}],
                }
            ],
        }


def _sentence_hash(edition):
    from django.conf import settings

    from almonium_book_processor.catalog.tasks import _edition_content_hash, _text_hash

    return _text_hash(
        edition.source_sha256,
        edition.language,
        settings.NLP_SPACY_MODELS.get(edition.language, "blank"),
        _edition_content_hash(edition),
    )


def test_the_run_names_the_edition_and_translates_its_contents(source, ukrainian):
    analysed(source, 1, ["Walton writes home from the far north."])
    analysed(source, 2, ["The expedition waits.", "A stranger is sighted."], level="B2")
    assert not title_page_current(ukrainian)
    PipelineRun.objects.create(
        edition=ukrainian,
        stage=PipelineRun.Stage.SENTENCES,
        status=PipelineRun.Status.SUCCEEDED,
        processor_version="test",
        input_hash=_sentence_hash(ukrainian),
        idempotency_key=f"{ukrainian.id}:sentences:test",
    )
    assert publication_blocker(ukrainian).startswith("Translate the title, author and blurb")

    run = queue_metadata_translation(str(ukrainian.id))
    provider = Provider()
    run_metadata_translation(run.id, provider=provider)

    run.refresh_from_db()
    ukrainian.refresh_from_db()
    assert run.status == PipelineRun.Status.SUCCEEDED
    assert provider.calls == ["title_page", "chapter_summary", "chapter_summary"]
    assert ukrainian.title == "Франкенштейн, або Сучасний Прометей"
    assert ukrainian.author == "Мері Шеллі"
    assert ukrainian.description == "Молодий науковець створює живу істоту й покидає її."
    assert ukrainian.public_description == ukrainian.description
    # The work is the original's: it keeps its English name and blurb.
    assert ukrainian.work.title == "Frankenstein; or, the Modern Prometheus"
    assert ukrainian.work.description.startswith("A young scientist")
    assert title_page_current(ukrainian)
    assert not publication_blocker(ukrainian).startswith("Translate the title")
    assert run.summary["chapters"] == 2 and run.summary["chapters_available"] == 2
    assert AIRun.objects.filter(pipeline_run=run, status=AIRun.Status.SUCCEEDED).count() == 3
    assert all(r.estimated_cost_usd > 0 for r in AIRun.objects.filter(pipeline_run=run))

    # Readers of the Ukrainian edition see the source's level and their own descriptions.
    chapters = public_chapters(ukrainian)
    assert [(c["sequence"], c["cefrEstimate"], c["analysisStatus"]) for c in chapters] == [
        (1, "C1", "complete"),
        (2, "B2", "complete"),
    ]
    assert chapters[0]["descriptions"] == ["UK: Walton writes home from the far north."]
    assert chapters[1]["descriptions"] == [
        "UK: The expedition waits.",
        "UK: A stranger is sighted.",
    ]
    assert chapters[0]["id"] == str(ukrainian.chapters.get(sequence=1).id)

    # Nothing changed at the source: asking again neither runs nor pays.
    again = queue_metadata_translation(str(ukrainian.id))
    assert again.id == run.id and again.status == PipelineRun.Status.SUCCEEDED
    run_metadata_translation(run.id, provider=provider)
    assert len(provider.calls) == 3


def test_a_translated_description_is_served_only_for_the_analysis_it_came_from(source, ukrainian):
    analysed(source, 1, ["Walton writes home."])
    run = queue_metadata_translation(str(ukrainian.id))
    run_metadata_translation(run.id, provider=Provider())
    assert public_chapters(ukrainian)[0]["descriptions"] == ["UK: Walton writes home."]

    # The source's analysis is refreshed with new wording: the old Ukrainian text
    # no longer describes it, and the chapter says so instead of showing English.
    source.artifacts.filter(chapter__sequence=1).update(is_current=False)
    analysed(source, 1, ["Walton writes to his sister."])
    chapters = public_chapters(ukrainian)
    assert chapters[0]["descriptions"] == []
    assert chapters[0]["analysisStatus"] == "pending"
    assert chapters[0]["cefrEstimate"] == "C1"
    # An unanalysed source chapter is simply pending, with no level to borrow.
    assert (chapters[1]["descriptions"], chapters[1]["cefrEstimate"]) == ([], None)

    # Only the changed chapter is paid for again; the title page is reused.
    provider = Provider()
    rerun = queue_metadata_translation(str(ukrainian.id))
    assert rerun.id != run.id
    run_metadata_translation(rerun.id, provider=provider)
    assert provider.calls == ["chapter_summary"]
    assert public_chapters(ukrainian)[0]["descriptions"] == ["UK: Walton writes to his sister."]


def test_a_failed_run_flags_the_edition_and_a_retry_reuses_finished_calls(source, ukrainian):
    analysed(source, 1, ["Walton writes home."])
    analysed(source, 2, ["The expedition waits."])
    run = queue_metadata_translation(str(ukrainian.id))
    provider = Provider(fail_chapter=2)

    with pytest.raises(RuntimeError):
        run_metadata_translation(run.id, provider=provider)

    run.refresh_from_db()
    ukrainian.refresh_from_db()
    assert run.status == PipelineRun.Status.FAILED
    # The title page answered, but the edition is named only when the run completes.
    assert ukrainian.title == source.title
    warning = ukrainian.warnings.get(code="translation_title_page", resolved_at=None)
    assert "still in the source language" in warning.message
    assert public_chapters(ukrainian)[0]["descriptions"] == []

    provider = Provider()
    retried = queue_metadata_translation(str(ukrainian.id))
    assert retried.id == run.id
    run_metadata_translation(run.id, provider=provider)
    ukrainian.refresh_from_db()
    assert provider.calls == ["chapter_summary"]
    assert ukrainian.title == "Франкенштейн, або Сучасний Прометей"
    assert not ukrainian.warnings.filter(code="translation_title_page", resolved_at=None).exists()


def test_a_transient_provider_error_is_retried_within_the_call(source, ukrainian, monkeypatch):
    monkeypatch.setattr(
        "almonium_book_processor.catalog.metadata_translation.time.sleep", lambda _: None
    )
    analysed(source, 1, ["Walton writes home."])
    run = queue_metadata_translation(str(ukrainian.id))
    provider = Provider(flaky_calls=2)

    run_metadata_translation(run.id, provider=provider)

    run.refresh_from_db()
    ukrainian.refresh_from_db()
    assert run.status == PipelineRun.Status.SUCCEEDED
    # Two empty 404s on the title page, then the answer; the chapter went first time.
    assert provider.calls == ["title_page", "title_page", "title_page", "chapter_summary"]
    assert ukrainian.title == "Франкенштейн, або Сучасний Прометей"

    # A third refusal is the provider's answer, not a blip: the run fails and says so.
    source.artifacts.filter(chapter__sequence=1).update(is_current=False)
    analysed(source, 1, ["Walton writes to his sister."])
    rerun = queue_metadata_translation(str(ukrainian.id))
    with pytest.raises(Flaky):
        run_metadata_translation(rerun.id, provider=Provider(flaky_calls=3))
    rerun.refresh_from_db()
    assert rerun.status == PipelineRun.Status.FAILED
    assert rerun.error.startswith("Flaky: Error code: 404")


def test_only_a_parallel_translation_is_named_from_its_source(source, ukrainian):
    adaptation = Edition.objects.create(
        work=source.work,
        slug="frankenstein-en-b2",
        source_edition=source,
        title=source.title,
        author=source.author,
        language="en",
        edition_type=Edition.EditionType.ADAPTATION,
        parallel_role=Edition.ParallelRole.PARALLEL,
        status=Edition.Status.READY,
    )
    assert not adaptation.is_parallel_translation
    with pytest.raises(ValueError, match="Only a parallel translation"):
        queue_metadata_translation(str(adaptation.id))
    with pytest.raises(ValueError, match="Only a parallel translation"):
        queue_metadata_translation(str(source.id))
    # The source's analysis finishing queues its translations, not its adaptation.
    runs = queue_for_translations_of(source)
    assert [run.edition_id for run in runs] == [ukrainian.id]


def test_the_page_offers_the_translation_and_borrows_the_sources_difficulty(
    client, source, ukrainian
):
    client.force_login(get_user_model().objects.create_user(username="staff", is_staff=True))
    page = client.get(reverse("catalog:edition-detail", args=[ukrainian.id])).content.decode()
    assert "Translate the title page and contents" in page
    assert "Analyze chapters with AI" not in page
    assert "Reading difficulty · borrowed from the source" in page
    source_page = client.get(reverse("catalog:edition-detail", args=[source.id])).content.decode()
    assert "Analyze chapters with AI" in source_page
    assert "Translate the title page" not in source_page

    response = client.post(
        reverse("catalog:queue-metadata-translation", args=[ukrainian.id]), follow=True
    )
    assert "Metadata translation queued" in response.content.decode()
    assert ukrainian.pipeline_runs.filter(
        stage=PipelineRun.Stage.TRANSLATE_METADATA, status=PipelineRun.Status.QUEUED
    ).exists()


def test_the_metadata_form_edits_a_derived_editions_own_blurb(client, source, ukrainian):
    client.force_login(get_user_model().objects.create_user(username="staff", is_staff=True))
    form = client.get(reverse("catalog:edition-detail", args=[ukrainian.id])).context[
        "metadata_form"
    ]
    assert form.initial["description"] == ""
    data = {name: value for name, value in form.initial.items() if value not in (None, "")}
    data["description"] = "Молодий науковець створює живу істоту."

    client.post(reverse("catalog:confirm-edition-metadata", args=[ukrainian.id]), data)

    ukrainian.refresh_from_db()
    assert ukrainian.description == "Молодий науковець створює живу істоту."
    assert ukrainian.work.description.startswith("A young scientist")


def test_the_public_api_and_publication_carry_the_editions_own_blurb(
    client, source, ukrainian, monkeypatch
):
    from almonium_book_processor.catalog.publication import publish_to_almonium

    sent = {}
    monkeypatch.setattr(
        "almonium_book_processor.catalog.publication._signed_post",
        lambda path, payload, failure: sent.update(payload) or {"bookId": "b"},
    )
    publish_to_almonium(ukrainian)
    assert sent["description"] == source.work.description

    Edition.objects.filter(id=ukrainian.id).update(
        description="Молодий науковець.", status=Edition.Status.PUBLISHED
    )
    ukrainian.refresh_from_db()
    publish_to_almonium(ukrainian)
    assert sent["description"] == "Молодий науковець."
    listed = client.get("/api/v1/public/editions/").json()
    rows = listed["results"] if isinstance(listed, dict) else listed
    assert {row["slug"]: row["description"] for row in rows} == {
        "frankenstein-en": source.work.description,
        "frankenstein-uk": "Молодий науковець.",
    }
