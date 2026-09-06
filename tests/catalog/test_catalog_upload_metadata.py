from __future__ import annotations

import json

import pytest
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from django.urls import reverse
from django.utils import timezone
from ebooklib import epub

from almonium_book_processor.catalog.forms import EditionUploadForm
from almonium_book_processor.catalog.metadata import (
    PROVISIONAL_SLUG_PREFIX,
    detect_metadata,
    form_provenance,
)
from almonium_book_processor.catalog.models import (
    AIRun,
    Chapter,
    ContentBlock,
    Edition,
    PipelineRun,
    Work,
)
from almonium_book_processor.catalog.services import create_source_edition
from almonium_book_processor.catalog.tasks import process_source_edition, publish_edition

pytestmark = pytest.mark.django_db


def epub_bytes(tmp_path, *, title="Upload Test", author="Ada Author", language="de") -> bytes:
    path = tmp_path / "upload.epub"
    book = epub.EpubBook()
    book.set_identifier("upload-test")
    book.set_title(title)
    book.set_language(language)
    book.add_author(author)
    chapter = epub.EpubHtml(title="One", file_name="one.xhtml", lang=language)
    chapter.content = "<h2>Eins</h2><p>Der erste Abschnitt.</p>"
    book.add_item(chapter)
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    book.spine = ["nav", chapter]
    epub.write_epub(path, book)
    return path.read_bytes()


def upload(tmp_path, name="upload.epub", **kwargs) -> SimpleUploadedFile:
    return SimpleUploadedFile(name, epub_bytes(tmp_path, **kwargs))


def fake_openai(monkeypatch, settings, *, proposal=None, error=None) -> dict:
    settings.OPENAI_API_KEY = "test-key"
    settings.OPENAI_METADATA_MODEL = "gpt-test"
    calls: dict = {"count": 0}
    monkeypatch.setattr(
        "almonium_book_processor.ai.openai_provider.OpenAIBatchProvider.__init__",
        lambda self: None,
    )

    def respond(self, body):
        calls["count"] += 1
        calls["body"] = body
        if error is not None:
            raise error
        return {
            "output": [
                {
                    "type": "message",
                    "content": [{"type": "output_text", "text": json.dumps(proposal)}],
                }
            ],
            "usage": {"input_tokens": 1000, "output_tokens": 80},
        }

    monkeypatch.setattr(
        "almonium_book_processor.ai.openai_provider.OpenAIBatchProvider.respond", respond
    )
    return calls


def test_upload_form_needs_only_the_file(tmp_path, monkeypatch, django_capture_on_commit_callbacks):
    queued: list[str] = []
    monkeypatch.setattr(
        "almonium_book_processor.catalog.tasks.process_book_pipeline.delay",
        lambda edition_id: queued.append(edition_id),
    )
    form = EditionUploadForm(data={}, files={"source_file": upload(tmp_path)})

    assert form.is_valid(), form.errors
    with django_capture_on_commit_callbacks(execute=True):
        edition = form.save()

    assert queued == [str(edition.id)]
    assert edition.slug.startswith(PROVISIONAL_SLUG_PREFIX)
    assert edition.work.slug.startswith(PROVISIONAL_SLUG_PREFIX)
    assert (edition.title, edition.author, edition.language) == ("", "", "")
    assert edition.cefr_level is None
    assert edition.edition_type == Edition.EditionType.ORIGINAL
    assert edition.work.metadata_provenance == {}
    assert [field.name for field in form.primary_fields] == [
        "edition_type",
        "source_edition",
        "cefr_level",
    ]
    assert "work_slug" in [field.name for field in form.override_fields]


def test_upload_form_records_pinned_fields_as_editorial(tmp_path) -> None:
    form = EditionUploadForm(
        data={"author": "Pinned Author", "language": "en", "publication_year": 1912},
        files={"source_file": upload(tmp_path)},
    )

    assert form.is_valid(), form.errors
    edition = form.save()

    assert edition.author == "Pinned Author"
    assert edition.language == "en"
    assert edition.work.publication_year == 1912
    assert edition.work.metadata_provenance == {
        "author": "user",
        "language": "user",
        "publication_year": "user",
    }


def test_catalog_upload_detects_metadata_and_finalizes_slugs(tmp_path, settings) -> None:
    settings.MEDIA_ROOT = tmp_path / "media"
    settings.OPENAI_API_KEY = ""
    edition = create_source_edition(source_file=upload(tmp_path))

    process_source_edition.run(str(edition.id))
    run = detect_metadata(str(edition.id))

    edition.refresh_from_db()
    work = edition.work
    assert run.status == PipelineRun.Status.SUCCEEDED
    assert (edition.title, edition.author, edition.language) == ("Upload Test", "Ada Author", "de")
    assert (work.title, work.author, work.original_language) == ("Upload Test", "Ada Author", "de")
    assert work.slug == "upload-test"
    assert edition.slug == "upload-test-de-original"
    assert work.metadata_provenance == {"title": "source", "author": "source", "language": "source"}
    assert work.metadata_detected_at is not None
    assert work.metadata_confirmed_at is None

    # The same file again does not collide with the first work.
    second = create_source_edition(source_file=upload(tmp_path, name="again.epub"))
    process_source_edition.run(str(second.id))
    detect_metadata(str(second.id))
    second.refresh_from_db()
    assert second.work.slug == "upload-test-2"
    assert second.slug == "upload-test-2-de-original"


def test_pinned_slugs_survive_detection(tmp_path, settings) -> None:
    settings.MEDIA_ROOT = tmp_path / "media"
    settings.OPENAI_API_KEY = ""
    edition = create_source_edition(
        source_file=upload(tmp_path), work_slug="my-work", edition_slug="my-work-de-first"
    )

    process_source_edition.run(str(edition.id))
    detect_metadata(str(edition.id))

    edition.refresh_from_db()
    assert edition.work.slug == "my-work"
    assert edition.slug == "my-work-de-first"
    assert edition.work.title == "Upload Test"


def test_fully_pinned_upload_skips_the_ai_call(tmp_path, settings, monkeypatch) -> None:
    settings.MEDIA_ROOT = tmp_path / "media"
    calls = fake_openai(monkeypatch, settings, error=AssertionError("must not be called"))
    edition = create_source_edition(
        source_file=upload(tmp_path),
        work_slug="pinned",
        work_title="Pinned Title",
        author="Pinned Author",
        description="Pinned description.",
        original_language="de",
        language="de",
        publication_year=1900,
        edition_slug="pinned-de-original",
        edition_title="Pinned Title",
    )

    process_source_edition.run(str(edition.id))
    run = detect_metadata(str(edition.id))

    assert calls["count"] == 0
    assert run.summary["open_fields"] == []
    assert not AIRun.objects.exists()
    edition.refresh_from_db()
    assert edition.work.title == "Pinned Title"


def test_ai_proposal_never_renames_the_work_through_a_translation(
    tmp_path, settings, monkeypatch
) -> None:
    work = Work.objects.create(
        slug="werk",
        title="Das Werk",
        author="Ada Author",
        original_language="de",
        metadata_provenance={"title": "source", "author": "source", "language": "source"},
    )
    source = Edition.objects.create(
        slug="werk-de-original", work=work, title="Das Werk", author="Ada Author", language="de"
    )
    translation = Edition.objects.create(
        slug="pending-abc",
        work=work,
        title="",
        author="",
        language="en",
        edition_type=Edition.EditionType.HUMAN_TRANSLATION,
        source_edition=source,
        source_sha256="c" * 64,
    )
    chapter = Chapter.objects.create(edition=translation, sequence=1)
    ContentBlock.objects.create(
        edition=translation,
        chapter=chapter,
        block_id="c1.p1",
        sequence=1,
        block_type=ContentBlock.BlockType.PARAGRAPH,
        text="The first section.",
    )
    fake_openai(
        monkeypatch,
        settings,
        proposal={
            "title": "The Work",
            "author": "Ada Author",
            "language": "en",
            "description": "A short work.",
            "publication_year": 1901,
            "note": "",
        },
    )

    detect_metadata(str(translation.id))

    translation.refresh_from_db()
    work.refresh_from_db()
    assert translation.title == "The Work"
    assert translation.slug == "werk-en-human"
    assert work.title == "Das Werk"
    assert work.original_language == "de"
    assert work.description == "A short work."
    assert work.publication_year == 1901
    assert work.metadata_provenance["title"] == "source"


def test_publication_refuses_provisional_slugs() -> None:
    work = Work.objects.create(
        slug="pending-work", title="Book", author="Author", original_language="de"
    )
    edition = Edition.objects.create(
        slug="pending-edition",
        work=work,
        title="Book",
        author="Author",
        language="de",
        status=Edition.Status.READY,
        cefr_level=Edition.CEFRLevel.B1,
    )

    with pytest.raises(ValueError, match="Confirm the detected metadata"):
        publish_edition.run(str(edition.id))


def test_staff_confirm_finalizes_metadata_and_slugs() -> None:
    work = Work.objects.create(
        slug="pending-1234",
        title="Upload Test",
        author="Ada Author",
        original_language="de",
        metadata_provenance={"title": "source", "author": "ai", "language": "source"},
        metadata_detected_at=timezone.now(),
    )
    edition = Edition.objects.create(
        slug="pending-5678",
        work=work,
        title="Upload Test",
        author="Ada Author",
        language="de",
        status=Edition.Status.READY,
    )
    staff = get_user_model().objects.create_user(
        username="editor", password="safe-test-password", is_staff=True
    )
    client = Client()
    client.force_login(staff)

    detail = client.get(reverse("catalog:edition-detail", args=[edition.id])).content.decode()
    assert "Detected · check and confirm" in detail
    assert "Slugs are still provisional." in detail
    assert 'provenance-ai">AI</em>' in detail

    response = client.post(
        reverse("catalog:confirm-edition-metadata", args=[edition.id]),
        {
            "work_slug": "upload-test",
            "work_title": "Upload Test",
            "author": "Ada Author",
            "description": "An editor-approved blurb.",
            "original_language": "de",
            "publication_year": 1912,
            "cover_url": "",
            "edition_slug": "upload-test-de-original",
            "edition_title": "Upload Test",
            "language": "de",
            "cefr_level": "B2",
        },
    )

    assert response.status_code == 302
    edition.refresh_from_db()
    work.refresh_from_db()
    assert (work.slug, edition.slug) == ("upload-test", "upload-test-de-original")
    assert work.description == "An editor-approved blurb."
    assert work.publication_year == 1912
    assert edition.cefr_level == Edition.CEFRLevel.B2
    assert work.metadata_confirmed_at is not None
    assert work.metadata_provenance["description"] == "user"
    assert work.metadata_provenance["work_slug"] == "user"
    assert edition.status == Edition.Status.READY
    detail = client.get(reverse("catalog:edition-detail", args=[edition.id])).content.decode()
    assert "Confirmed</span>" in detail


def test_staff_confirm_rejects_invalid_slug() -> None:
    work = Work.objects.create(slug="w", title="T", author="A", original_language="de")
    edition = Edition.objects.create(slug="e", work=work, title="T", author="A", language="de")
    staff = get_user_model().objects.create_user(
        username="editor", password="safe-test-password", is_staff=True
    )
    client = Client()
    client.force_login(staff)

    response = client.post(
        reverse("catalog:confirm-edition-metadata", args=[edition.id]),
        {
            "work_slug": "not a slug",
            "work_title": "T",
            "author": "A",
            "original_language": "de",
            "edition_slug": "e",
            "edition_title": "T",
            "language": "de",
        },
    )

    assert response.status_code == 200
    assert "Fix the highlighted metadata fields." in response.content.decode()
    work.refresh_from_db()
    assert work.slug == "w"


def test_upload_page_offers_pins_as_optional() -> None:
    staff = get_user_model().objects.create_user(
        username="editor", password="safe-test-password", is_staff=True
    )
    client = Client()
    client.force_login(staff)

    page = client.get(reverse("catalog:upload")).content.decode()

    assert "Only the file is required." in page
    assert "Pin details by hand" in page
    assert "Detect from the file" in page


def test_metadata_run_note_names_who_chose_each_field() -> None:
    run = PipelineRun(
        stage=PipelineRun.Stage.METADATA,
        summary={
            "ai_enabled": True,
            "ai_status": AIRun.Status.SUCCEEDED,
            "open_fields": ["title", "description", "publication_year"],
            "provenance": {
                "title": "ai",
                "author": "source",
                "description": "ai",
                "language": "source",
                "publication_year": "ai",
            },
        },
    )

    assert run.summary_note == (
        "AI proposed title, blurb, first-published year · file header supplied author, language"
    )


@pytest.mark.parametrize(
    ("summary", "expected"),
    [
        (
            {"ai_enabled": False, "open_fields": ["title"], "provenance": {"title": "source"}},
            "file header supplied title · no model configured",
        ),
        (
            {"ai_enabled": True, "open_fields": [], "provenance": {"title": "user"}},
            "editor pinned title · every field was pinned, so no model was called",
        ),
        (
            {
                "ai_enabled": True,
                "ai_status": AIRun.Status.FAILED,
                "open_fields": ["title"],
                "provenance": {"title": "source"},
            },
            "file header supplied title · the model call did not complete",
        ),
    ],
)
def test_metadata_run_note_explains_a_missing_model_call(summary, expected) -> None:
    assert PipelineRun(stage=PipelineRun.Stage.METADATA, summary=summary).summary_note == expected


def test_other_stages_and_unfinished_runs_have_no_note() -> None:
    assert PipelineRun(stage=PipelineRun.Stage.LEXICAL, summary={"words": 1}).summary_note == ""
    assert PipelineRun(stage=PipelineRun.Stage.METADATA, summary={}).summary_note == ""


def test_edition_page_shows_metadata_provenance_in_the_panel_and_the_history() -> None:
    provenance = {
        "title": "ai",
        "author": "source",
        "description": "ai",
        "language": "source",
        "publication_year": "ai",
    }
    work = Work.objects.create(
        slug="detected",
        title="Detected Title",
        author="Ada Author",
        description="A detected blurb.",
        original_language="de",
        publication_year=1912,
        metadata_provenance=provenance,
        metadata_detected_at=timezone.now(),
    )
    edition = Edition.objects.create(
        slug="detected-de-original",
        work=work,
        title="Detected Title",
        author="Ada Author",
        language="de",
        status=Edition.Status.READY,
    )
    PipelineRun.objects.create(
        edition=edition,
        stage=PipelineRun.Stage.METADATA,
        status=PipelineRun.Status.SUCCEEDED,
        idempotency_key=f"{edition.id}:metadata",
        processor_version="test",
        input_hash="0" * 64,
        summary={
            "ai_enabled": True,
            "ai_status": AIRun.Status.SUCCEEDED,
            "open_fields": list(provenance),
            "provenance": provenance,
        },
    )
    staff = get_user_model().objects.create_user(
        username="history-editor", password="safe-test-password", is_staff=True
    )
    client = Client()
    client.force_login(staff)

    detail = client.get(reverse("catalog:edition-detail", args=[edition.id])).content.decode()

    assert "AI proposed title, blurb, first-published year" in detail
    assert "file header supplied author, language" in detail
    # Work title and language are tagged too: the form names them differently
    # from the provenance keys, and both are the fields a model is most likely
    # to have chosen.
    assert detail.count('provenance-ai">AI</em>') == 4  # both titles, blurb, year
    assert detail.count('provenance-source">file</em>') == 3  # author, both languages


def test_a_translation_does_not_borrow_the_work_provenance_for_its_own_fields() -> None:
    work = Work.objects.create(
        slug="werk",
        title="Werk",
        author="Ada Author",
        original_language="de",
        metadata_provenance={"title": "ai", "language": "ai"},
    )
    Edition.objects.create(
        slug="werk-de-original", work=work, title="Werk", author="Ada Author", language="de"
    )
    translation = Edition.objects.create(
        slug="werk-en-human",
        work=work,
        title="Work",
        author="Ada Author",
        language="en",
        edition_type=Edition.EditionType.HUMAN_TRANSLATION,
    )

    assert set(form_provenance(translation)) == {"work_title", "original_language"}
