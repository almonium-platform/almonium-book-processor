"""The product API orders translations and library ingests as jobs it can watch."""

from __future__ import annotations

import math
import uuid
from decimal import Decimal

import pytest
from django.core.files.base import ContentFile
from rest_framework.test import APIClient

from almonium_book_processor.ai.translation import (
    TRANSLATION_SYSTEM_PROMPT,
    TRANSLATION_USER_TEMPLATE,
)
from almonium_book_processor.catalog import translation_jobs
from almonium_book_processor.catalog.ai_translation import PROMPT_NAME, TRANSLATION_MODEL_PRICING
from almonium_book_processor.catalog.models import (
    AIRun,
    Chapter,
    ContentBlock,
    Edition,
    ModelConfiguration,
    PromptTemplate,
    Work,
)
from almonium_book_processor.catalog.publication import publish_to_almonium
from almonium_book_processor.catalog.translation_jobs import (
    JobConflict,
    cancel_translation,
    continue_after_translation,
    estimate_translation,
    translation_status,
)

pytestmark = pytest.mark.django_db

SECRET = "test-shared-secret"
HEADERS = {"HTTP_X_ALMONIUM_BOOKS_TOKEN": SECRET}
CHAPTER_TEXTS = (("Chapter I", "It was a dark and stormy night."), ("Chapter II", "The end."))


@pytest.fixture(autouse=True)
def shared_secret(monkeypatch):
    monkeypatch.setenv("ALMONIUM_BOOKS_PUBLISHER_TOKEN", SECRET)


def published_canonical(*, cefr_level="B2") -> Edition:
    work = Work.objects.create(
        slug=f"effi-{uuid.uuid4().hex[:6]}",
        title="Effi Briest",
        author="Theodor Fontane",
        original_language="de",
        publication_year=1895,
    )
    edition = Edition.objects.create(
        slug=f"{work.slug}-de-original",
        work=work,
        title=work.title,
        author=work.author,
        language="de",
        source_sha256="a" * 64,
        status=Edition.Status.PUBLISHED,
        cefr_level=cefr_level,
        published_book_id=uuid.uuid4(),
    )
    for sequence, (heading, paragraph) in enumerate(CHAPTER_TEXTS, start=1):
        chapter = Chapter.objects.create(edition=edition, sequence=sequence, title=heading)
        ContentBlock.objects.create(
            edition=edition,
            chapter=chapter,
            block_id=f"c{sequence}.h1",
            sequence=1,
            block_type=ContentBlock.BlockType.HEADING,
            text=heading,
            align_group=uuid.uuid4(),
        )
        ContentBlock.objects.create(
            edition=edition,
            chapter=chapter,
            block_id=f"c{sequence}.p2",
            sequence=2,
            block_type=ContentBlock.BlockType.PARAGRAPH,
            text=paragraph,
            align_group=uuid.uuid4(),
        )
    return edition


def private_import(*, owner_id=None) -> Edition:
    import_id = uuid.uuid4()
    work = Work.objects.create(
        slug=f"private-{import_id}",
        title="Der Schimmelreiter",
        author="Theodor Storm",
        original_language="de",
        publication_year=1888,
        visibility=Work.Visibility.PRIVATE,
        owner_id=owner_id or uuid.uuid4(),
        owner_label="private-reader",
    )
    edition = Edition.objects.create(
        id=import_id,
        slug=work.slug,
        work=work,
        title=work.title,
        author=work.author,
        language="de",
        status=Edition.Status.READY,
        source_sha256="b" * 64,
    )
    edition.source_file.save("schimmelreiter.epub", ContentFile(b"epub bytes"), save=True)
    return edition


def translation_run(edition, *, status, execution="batch", counts=None, cost="0.40") -> AIRun:
    configuration, _ = ModelConfiguration.objects.get_or_create(
        name="openai-translation-quality-v1",
        defaults={"provider": "openai", "model": "gpt-test", "purpose": "literary_translation"},
    )
    template, _ = PromptTemplate.objects.get_or_create(
        name=PROMPT_NAME,
        version=1,
        defaults={"purpose": "literary_translation", "system_prompt": "s", "user_template": "u"},
    )
    return AIRun.objects.create(
        edition=edition,
        model_configuration=configuration,
        prompt_template=template,
        status=status,
        provider_request_id="batch_123" if execution == "batch" else "direct:x",
        request_payload={"execution": execution, "tier": "quality"},
        response_payload={"request_counts": counts} if counts else {},
        estimated_cost_usd=Decimal(cost),
    )


def stub_queues(monkeypatch) -> dict:
    calls: dict = {"batch": [], "inline": []}
    monkeypatch.setattr(
        "almonium_book_processor.catalog.tasks.prepare_translation.delay",
        lambda *args, **kwargs: calls["batch"].append((args, kwargs)),
    )
    monkeypatch.setattr(
        "almonium_book_processor.catalog.tasks.translate_edition_inline.delay",
        lambda *args, **kwargs: calls["inline"].append((args, kwargs)),
    )
    return calls


# --- A1 estimate -------------------------------------------------------------


def test_the_estimate_prices_every_chapter_with_its_prompt_and_halves_for_batch() -> None:
    edition = published_canonical()

    estimate = estimate_translation(
        edition_slug=edition.slug, target_language="uk", tier="quality", mode="batch"
    )

    prompt_tokens = math.ceil((len(TRANSLATION_SYSTEM_PROMPT) + len(TRANSLATION_USER_TEMPLATE)) / 4)
    input_tokens = output_tokens = 0
    for heading, paragraph in CHAPTER_TEXTS:
        text_tokens = math.ceil((len(heading) + len(paragraph)) / 4)
        input_tokens += text_tokens + prompt_tokens
        output_tokens += math.ceil(text_tokens * Decimal("1.15")) + 24 * 2
    pricing = TRANSLATION_MODEL_PRICING["quality"]
    expected = (
        Decimal(input_tokens) * Decimal(pricing["input"])
        + Decimal(output_tokens) * Decimal(pricing["output"])
    ) / Decimal(1_000_000)
    expected = (expected * Decimal("0.5")).quantize(Decimal("0.000001"))

    assert estimate["chapters"] == 2
    assert estimate["blocks"] == 4
    assert estimate["source_chars"] == sum(len(h) + len(p) for h, p in CHAPTER_TEXTS)
    assert estimate["estimated_input_tokens"] == input_tokens
    assert estimate["estimated_output_tokens"] == output_tokens
    assert Decimal(estimate["estimated_cost_usd"]) == expected

    direct = estimate_translation(
        edition_slug=edition.slug, target_language="uk", tier="quality", mode="inline"
    )
    assert Decimal(direct["estimated_cost_usd"]) == Decimal(estimate["estimated_cost_usd"]) * 2


def test_the_estimate_endpoint_guards_its_inputs() -> None:
    edition = published_canonical()
    client = APIClient()

    ok = client.get(
        "/api/v1/internal/translations/estimate/",
        {"edition_slug": edition.slug, "target_language": "uk"},
        **HEADERS,
    )
    assert ok.status_code == 200
    assert ok.json()["tier"] == "quality"

    missing = client.get(
        "/api/v1/internal/translations/estimate/",
        {"edition_slug": "nope", "target_language": "uk"},
        **HEADERS,
    )
    assert missing.status_code == 404

    same_language = client.get(
        "/api/v1/internal/translations/estimate/",
        {"edition_slug": edition.slug, "target_language": "de"},
        **HEADERS,
    )
    assert same_language.status_code == 400

    unauthenticated = client.get(
        "/api/v1/internal/translations/estimate/",
        {"edition_slug": edition.slug, "target_language": "uk"},
    )
    assert unauthenticated.status_code in {401, 403}


def test_an_unpublished_edition_is_not_estimated() -> None:
    edition = published_canonical()
    edition.status = Edition.Status.READY
    edition.save(update_fields=["status"])

    response = APIClient().get(
        "/api/v1/internal/translations/estimate/",
        {"edition_slug": edition.slug, "target_language": "uk"},
        **HEADERS,
    )

    assert response.status_code == 404


# --- A2 start --------------------------------------------------------------


def test_starting_a_job_is_idempotent_and_copies_the_source_level(
    monkeypatch, django_capture_on_commit_callbacks
) -> None:
    source = published_canonical(cefr_level="B2")
    calls = stub_queues(monkeypatch)
    job_id = uuid.uuid4()
    body = {"job_id": str(job_id), "edition_slug": source.slug, "target_language": "uk"}
    client = APIClient()

    with django_capture_on_commit_callbacks(execute=True):
        first = client.post("/api/v1/internal/translations/", body, format="json", **HEADERS)
    assert first.status_code == 202, first.content
    payload = first.json()
    assert payload["phase"] == "translating"
    assert payload["source_edition_slug"] == source.slug
    assert payload["target_language"] == "uk"
    edition = Edition.objects.get(id=payload["edition_id"])
    assert edition.external_job_id == job_id
    assert edition.auto_publish is True
    assert edition.cefr_level == "B2"
    assert edition.edition_type == Edition.EditionType.MACHINE_TRANSLATION
    assert calls["batch"] == [((str(edition.id),), {"tier": "quality"})]

    second = client.post("/api/v1/internal/translations/", body, format="json", **HEADERS)
    assert second.status_code == 200
    assert second.json()["edition_id"] == str(edition.id)
    assert Edition.objects.filter(external_job_id=job_id).count() == 1
    assert len(calls["batch"]) == 1


def test_inline_mode_runs_directly_and_a_draft_tier_is_honoured(
    monkeypatch, django_capture_on_commit_callbacks
) -> None:
    source = published_canonical()
    calls = stub_queues(monkeypatch)

    with django_capture_on_commit_callbacks(execute=True):
        response = APIClient().post(
            "/api/v1/internal/translations/",
            {
                "job_id": str(uuid.uuid4()),
                "edition_slug": source.slug,
                "target_language": "en",
                "tier": "draft",
                "mode": "inline",
                "auto_publish": False,
            },
            format="json",
            **HEADERS,
        )

    assert response.status_code == 202
    edition = Edition.objects.get(id=response.json()["edition_id"])
    assert edition.auto_publish is False
    assert calls["inline"] == [((str(edition.id), "draft"), {})]
    assert calls["batch"] == []


def test_starting_a_job_rejects_an_unknown_edition_and_a_bad_language(monkeypatch) -> None:
    source = published_canonical()
    stub_queues(monkeypatch)
    client = APIClient()

    missing = client.post(
        "/api/v1/internal/translations/",
        {"job_id": str(uuid.uuid4()), "edition_slug": "nope", "target_language": "uk"},
        format="json",
        **HEADERS,
    )
    assert missing.status_code == 404

    bad = client.post(
        "/api/v1/internal/translations/",
        {"job_id": str(uuid.uuid4()), "edition_slug": source.slug, "target_language": "xx"},
        format="json",
        **HEADERS,
    )
    assert bad.status_code == 400


# --- A3 status -------------------------------------------------------------


def started_job(source=None, **overrides) -> Edition:
    source = source or published_canonical()
    fields = {
        "slug": f"{source.work.slug}-uk-parallel",
        "work": source.work,
        "source_edition": source,
        "title": source.title,
        "author": source.author,
        "language": "uk",
        "edition_type": Edition.EditionType.MACHINE_TRANSLATION,
        "parallel_role": Edition.ParallelRole.PARALLEL,
        "translator": "AI (contemporary neutral)",
        "literary_register": Edition.LiteraryRegister.CONTEMPORARY,
        "external_job_id": uuid.uuid4(),
        "auto_publish": True,
        "status": Edition.Status.PROCESSING,
    }
    return Edition.objects.create(**{**fields, **overrides})


def test_status_reports_each_phase_and_the_batch_progress() -> None:
    edition = started_job()
    assert translation_status(edition)["phase"] == "translating"
    assert translation_status(edition)["progress"] is None

    run = translation_run(
        edition, status=AIRun.Status.SUBMITTED, counts={"completed": 9, "total": 24, "failed": 0}
    )
    status = translation_status(edition)
    assert status["phase"] == "translating"
    assert status["progress"] == {"completed": 9, "total": 24}
    assert status["estimated_cost_usd"] == "0.400000"

    run.status = AIRun.Status.SUCCEEDED
    run.save(update_fields=["status"])
    assert translation_status(edition)["phase"] == "aligning"

    for edition_status, phase in (
        (Edition.Status.REVIEW, "qa_gate"),
        (Edition.Status.READY, "publishing"),
        (Edition.Status.PUBLISHED, "published"),
        (Edition.Status.FAILED, "failed"),
    ):
        edition.status = edition_status
        edition.save(update_fields=["status"])
        assert translation_status(edition)["phase"] == phase


def test_status_is_served_only_for_ordered_translations() -> None:
    edition = started_job()
    client = APIClient()

    found = client.get(f"/api/v1/internal/translations/{edition.id}/", **HEADERS)
    assert found.status_code == 200
    assert found.json()["edition_slug"] == edition.slug

    staff_made = started_job(external_job_id=None)
    assert (
        client.get(f"/api/v1/internal/translations/{staff_made.id}/", **HEADERS).status_code == 404
    )


# --- A4 cancel -------------------------------------------------------------


def test_cancelling_stops_the_batch_and_fails_the_run_and_the_edition(monkeypatch) -> None:
    edition = started_job()
    run = translation_run(edition, status=AIRun.Status.SUBMITTED)
    cancelled: list[str] = []
    monkeypatch.setattr(
        "almonium_book_processor.ai.openai_provider.OpenAIBatchProvider.__init__",
        lambda self: None,
    )
    monkeypatch.setattr(
        "almonium_book_processor.ai.openai_provider.OpenAIBatchProvider.cancel",
        lambda self, batch_id: cancelled.append(batch_id),
    )

    response = APIClient().post(f"/api/v1/internal/translations/{edition.id}/cancel/", **HEADERS)

    assert response.status_code == 200
    assert response.json()["phase"] == "failed"
    assert cancelled == ["batch_123"]
    run.refresh_from_db()
    edition.refresh_from_db()
    assert run.status == AIRun.Status.FAILED
    assert run.error == "Cancelled by operator"
    assert run.finished_at is not None
    assert edition.status == Edition.Status.FAILED
    assert edition.auto_publish is False


def test_a_provider_that_will_not_cancel_does_not_stop_the_cancellation(monkeypatch) -> None:
    edition = started_job()
    translation_run(edition, status=AIRun.Status.SUBMITTED)
    monkeypatch.setattr(
        "almonium_book_processor.ai.openai_provider.OpenAIBatchProvider.__init__",
        lambda self: (_ for _ in ()).throw(RuntimeError("OPENAI_API_KEY is not configured")),
    )

    cancel_translation(edition)

    edition.refresh_from_db()
    assert edition.status == Edition.Status.FAILED


def test_a_published_translation_cannot_be_cancelled() -> None:
    edition = started_job(status=Edition.Status.PUBLISHED)

    with pytest.raises(JobConflict):
        cancel_translation(edition)
    response = APIClient().post(f"/api/v1/internal/translations/{edition.id}/cancel/", **HEADERS)
    assert response.status_code == 409


# --- auto-publish chain ------------------------------------------------------


class FakeSignature:
    def __init__(self, log, name, args):
        self.log = log
        self.steps = [(name, args)]

    def __or__(self, other):
        self.steps.extend(other.steps)
        return self

    def delay(self):
        self.log.append(("chain", list(self.steps)))


class FakeTask:
    def __init__(self, log, name):
        self.log = log
        self.name = name

    def si(self, *args):
        return FakeSignature(self.log, self.name, args)

    def delay(self, *args):
        self.log.append((self.name, args))


def test_an_ordered_translation_that_lands_clean_goes_out_after_its_split(monkeypatch) -> None:
    log: list = []
    monkeypatch.setattr(
        "almonium_book_processor.catalog.tasks.split_edition_sentences", FakeTask(log, "split")
    )
    monkeypatch.setattr(
        "almonium_book_processor.catalog.tasks.publish_edition", FakeTask(log, "publish")
    )
    edition = started_job(status=Edition.Status.READY)

    assert continue_after_translation(str(edition.id)) is True
    assert log == [("chain", [("split", (str(edition.id),)), ("publish", (str(edition.id),))])]


@pytest.mark.parametrize(
    ("status", "auto_publish"),
    [(Edition.Status.REVIEW, True), (Edition.Status.READY, False)],
)
def test_a_translation_that_needs_review_or_was_not_ordered_only_gets_its_split(
    monkeypatch, status, auto_publish
) -> None:
    log: list = []
    monkeypatch.setattr(
        "almonium_book_processor.catalog.tasks.split_edition_sentences", FakeTask(log, "split")
    )
    monkeypatch.setattr(
        "almonium_book_processor.catalog.tasks.publish_edition", FakeTask(log, "publish")
    )
    edition = started_job(status=status, auto_publish=auto_publish)

    assert continue_after_translation(str(edition.id)) is False
    assert log == [("split", (str(edition.id),))]


# --- A5/A6 library ingest ----------------------------------------------------


def test_a_library_ingest_copies_the_upload_into_a_new_public_edition(monkeypatch) -> None:
    source = private_import()
    suggestion_id = uuid.uuid4()
    body = {
        "suggestion_id": str(suggestion_id),
        "import_id": str(source.id),
        "owner_id": str(source.work.owner_id),
        "title": "Der Schimmelreiter",
        "author": "Theodor Storm",
        "description": "A dyke-master's tale.",
        "language": "de",
        "publication_year": 1888,
    }
    client = APIClient()

    first = client.post("/api/v1/internal/library-ingests/", body, format="json", **HEADERS)

    assert first.status_code == 202, first.content
    payload = first.json()
    assert payload["phase"] == "ingesting"
    edition = Edition.objects.select_related("work").get(id=payload["edition_id"])
    assert edition.id != source.id
    assert edition.work.visibility == Work.Visibility.PUBLIC
    assert edition.work.owner_id is None
    assert edition.work.title == "Der Schimmelreiter"
    assert edition.work.publication_year == 1888
    assert edition.language == "de"
    assert edition.external_job_id == suggestion_id
    assert edition.status == Edition.Status.QUEUED
    assert edition.source_file.name != source.source_file.name
    with edition.source_file.open("rb") as stream:
        assert stream.read() == b"epub bytes"
    source.refresh_from_db()
    assert source.work.visibility == Work.Visibility.PRIVATE

    second = client.post("/api/v1/internal/library-ingests/", body, format="json", **HEADERS)
    assert second.status_code == 200
    assert second.json()["edition_id"] == str(edition.id)

    status = client.get(f"/api/v1/internal/library-ingests/{edition.id}/", **HEADERS)
    assert status.status_code == 200
    assert status.json()["slug"] == edition.slug


def test_a_library_ingest_needs_the_owner_of_the_import() -> None:
    source = private_import()

    response = APIClient().post(
        "/api/v1/internal/library-ingests/",
        {
            "suggestion_id": str(uuid.uuid4()),
            "import_id": str(source.id),
            "owner_id": str(uuid.uuid4()),
            "title": "Der Schimmelreiter",
            "author": "Theodor Storm",
            "language": "de",
        },
        format="json",
        **HEADERS,
    )

    assert response.status_code == 404
    assert Edition.objects.filter(work__visibility=Work.Visibility.PUBLIC).count() == 0


def test_ingest_status_maps_the_edition_state() -> None:
    edition = published_canonical()
    edition.external_job_id = uuid.uuid4()
    edition.save(update_fields=["external_job_id"])
    for status, phase in (
        (Edition.Status.PROCESSING, "ingesting"),
        (Edition.Status.REVIEW, "review"),
        (Edition.Status.READY, "ready"),
        (Edition.Status.PUBLISHED, "published"),
        (Edition.Status.FAILED, "failed"),
    ):
        edition.status = status
        edition.save(update_fields=["status"])
        assert translation_jobs.library_ingest_status(edition)["phase"] == phase


# --- A7 source download ------------------------------------------------------


def test_the_owner_s_upload_streams_back_for_a_reviewer() -> None:
    source = private_import()
    client = APIClient()

    response = client.get(
        f"/api/v1/internal/imports/{source.id}/source/?owner_id={source.work.owner_id}", **HEADERS
    )
    assert response.status_code == 200
    assert "attachment" in response["Content-Disposition"]
    assert b"".join(response.streaming_content) == b"epub bytes"

    foreign = client.get(
        f"/api/v1/internal/imports/{source.id}/source/?owner_id={uuid.uuid4()}", **HEADERS
    )
    assert foreign.status_code == 404


# --- A8 publication payload --------------------------------------------------


def test_the_publication_payload_names_the_edition_and_the_job_that_asked_for_it(
    monkeypatch,
) -> None:
    edition = started_job(status=Edition.Status.READY)
    sent: dict = {}

    def fake_signed_post(path, payload, *, failure):
        sent["path"] = path
        sent["payload"] = payload
        return {"bookId": str(uuid.uuid4())}

    monkeypatch.setattr(
        "almonium_book_processor.catalog.publication._signed_post", fake_signed_post
    )

    publish_to_almonium(edition)

    assert sent["path"] == "/internal/books/publications"
    assert sent["payload"]["editionId"] == str(edition.id)
    assert sent["payload"]["externalJobId"] == str(edition.external_job_id)
    # The count a shelf says "chapter 3 of 24" against comes from here, not from a client.
    assert sent["payload"]["chapterCount"] == edition.chapters.count()

    edition.external_job_id = None
    publish_to_almonium(edition)
    assert sent["payload"]["externalJobId"] is None


# --- A9 re-create after delete ------------------------------------------------


def test_a_deleted_import_can_be_uploaded_again_under_the_same_id(tmp_path, settings) -> None:
    settings.MEDIA_ROOT = tmp_path / "media"
    source = private_import()
    owner_id = source.work.owner_id
    client = APIClient()

    deleted = client.delete(f"/api/v1/internal/imports/{source.id}/?owner_id={owner_id}", **HEADERS)
    assert deleted.status_code == 204

    from django.core.files.uploadedfile import SimpleUploadedFile

    recreated = client.post(
        "/api/v1/internal/imports/",
        {
            "import_id": str(source.id),
            "owner_id": str(owner_id),
            "owner_label": "private-reader",
            "title": "Der Schimmelreiter",
            "author": "Theodor Storm",
            "language": "de",
            "source_file": SimpleUploadedFile("again.epub", b"new bytes"),
        },
        **HEADERS,
    )

    assert recreated.status_code == 202, recreated.content
    edition = Edition.objects.select_related("work").get(id=source.id)
    assert edition.status == Edition.Status.QUEUED
    assert edition.work.owner_id == owner_id
    assert edition.title == "Der Schimmelreiter"
