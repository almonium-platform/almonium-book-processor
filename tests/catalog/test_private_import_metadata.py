from __future__ import annotations

import json
import uuid

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from ebooklib import epub
from rest_framework.test import APIClient

from almonium_book_processor.catalog.import_events import send_private_import_event
from almonium_book_processor.catalog.metadata import (
    PROMPT_NAME,
    confirm_metadata,
    detect_metadata,
)
from almonium_book_processor.catalog.models import (
    AIRun,
    Chapter,
    ContentBlock,
    Edition,
    PipelineRun,
    Work,
)
from almonium_book_processor.catalog.tasks import process_source_edition

pytestmark = pytest.mark.django_db

SECRET = "test-shared-secret"


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


def private_edition(**metadata) -> Edition:
    provenance = {name: "user" for name, value in metadata.items() if value not in (None, "")}
    work = Work.objects.create(
        slug=f"private-{uuid.uuid4()}",
        title=metadata.get("title", ""),
        author=metadata.get("author", ""),
        description=metadata.get("description", ""),
        original_language=metadata.get("language", ""),
        publication_year=metadata.get("publication_year"),
        visibility=Work.Visibility.PRIVATE,
        owner_id=uuid.uuid4(),
        owner_label="private-reader",
        metadata_provenance=provenance,
    )
    edition = Edition.objects.create(
        slug=work.slug,
        work=work,
        title=work.title,
        author=work.author,
        language=work.original_language,
        source_sha256="b" * 64,
        status=Edition.Status.READY,
    )
    chapter = Chapter.objects.create(edition=edition, sequence=1, title="Chapter I")
    for sequence, (block_type, text) in enumerate(
        (
            (ContentBlock.BlockType.HEADING, "Chapter I"),
            (ContentBlock.BlockType.PARAGRAPH, "It was a dark and stormy night."),
        ),
        start=1,
    ):
        ContentBlock.objects.create(
            edition=edition,
            chapter=chapter,
            block_id=f"c1.b{sequence}",
            sequence=sequence,
            block_type=block_type,
            text=text,
        )
    return edition


def fake_openai(monkeypatch, settings, *, proposal=None, error=None) -> dict:
    """Stand in for the direct Responses call; never touches the network."""

    settings.OPENAI_API_KEY = "test-key"
    settings.OPENAI_METADATA_MODEL = "gpt-test"
    calls: dict = {}
    monkeypatch.setattr(
        "almonium_book_processor.ai.openai_provider.OpenAIBatchProvider.__init__",
        lambda self: None,
    )

    def respond(self, body):
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
            "usage": {
                "input_tokens": 1200,
                "output_tokens": 90,
                "input_tokens_details": {"cached_tokens": 200},
                "output_tokens_details": {"reasoning_tokens": 30},
            },
        }

    monkeypatch.setattr(
        "almonium_book_processor.ai.openai_provider.OpenAIBatchProvider.respond", respond
    )
    return calls


def test_header_only_upload_adopts_file_metadata(tmp_path, monkeypatch, settings) -> None:
    settings.MEDIA_ROOT = tmp_path / "media"
    settings.OPENAI_API_KEY = ""
    monkeypatch.setenv("ALMONIUM_BOOKS_PUBLISHER_TOKEN", SECRET)
    owner_id = uuid.uuid4()
    client = APIClient()

    response = client.post(
        "/api/v1/internal/imports/",
        {
            "import_id": str(uuid.uuid4()),
            "owner_id": str(owner_id),
            "owner_label": "private-reader",
            "source_file": SimpleUploadedFile("private.epub", epub_bytes(tmp_path)),
        },
        format="multipart",
        HTTP_X_ALMONIUM_BOOKS_TOKEN=SECRET,
    )

    assert response.status_code == 202, response.data
    assert response.data["metadata"] == {
        "title": "",
        "author": "",
        "description": "",
        "language": None,
        "publication_year": None,
        "provenance": {},
        "detected": False,
    }
    edition = Edition.objects.select_related("work").get(id=response.data["id"])

    process_source_edition.run(str(edition.id))
    run = detect_metadata(str(edition.id))

    edition.refresh_from_db()
    assert (edition.title, edition.author, edition.language) == ("Upload Test", "Ada Author", "de")
    assert (edition.work.title, edition.work.original_language) == ("Upload Test", "de")
    assert edition.work.metadata_provenance == {
        "title": "source",
        "author": "source",
        "language": "source",
    }
    assert edition.work.metadata_detected_at is not None
    assert run.stage == PipelineRun.Stage.METADATA
    assert run.status == PipelineRun.Status.SUCCEEDED
    assert run.summary["ai_enabled"] is False
    assert not AIRun.objects.exists()

    detail = client.get(
        f"/api/v1/internal/imports/{edition.id}/",
        {"owner_id": str(owner_id)},
        HTTP_X_ALMONIUM_BOOKS_TOKEN=SECRET,
    )
    assert detail.data["metadata"]["detected"] is True
    assert detail.data["metadata"]["language"] == "de"


def test_ai_proposal_fills_gaps_but_never_overrides_the_owner(monkeypatch, settings) -> None:
    edition = private_edition(title="", author="", language="de")
    edition.title = edition.work.title = "UNKNOWN"
    edition.author = edition.work.author = "Author, Ada"
    edition.save()
    edition.work.metadata_provenance = {"language": "user", "title": "source", "author": "source"}
    edition.work.save()
    calls = fake_openai(
        monkeypatch,
        settings,
        proposal={
            "title": "A Stormy Night",
            "author": "Ada Author",
            "language": "en",
            "description": "A short novel about weather.",
            "publication_year": 1912,
            "note": "Normalised the author name.",
        },
    )

    run = detect_metadata(str(edition.id))

    edition.refresh_from_db()
    work = edition.work
    assert (edition.title, edition.author) == ("A Stormy Night", "Ada Author")
    assert (work.title, work.author) == ("A Stormy Night", "Ada Author")
    # The owner chose German at upload; the model's opinion does not override it.
    assert (edition.language, work.original_language) == ("de", "de")
    assert work.description == "A short novel about weather."
    assert work.publication_year == 1912
    assert work.metadata_provenance == {
        "title": "ai",
        "author": "ai",
        "language": "user",
        "description": "ai",
        "publication_year": "ai",
    }
    assert run.status == PipelineRun.Status.SUCCEEDED

    ai_run = AIRun.objects.get()
    assert ai_run.status == AIRun.Status.SUCCEEDED
    assert ai_run.pipeline_run_id == run.id
    assert ai_run.prompt_template.name == PROMPT_NAME
    assert ai_run.model_configuration.model == "gpt-test"
    assert (ai_run.input_tokens, ai_run.cached_input_tokens, ai_run.output_tokens) == (
        1200,
        200,
        90,
    )
    assert ai_run.reasoning_tokens == 30
    assert ai_run.estimated_cost_usd > 0
    assert ai_run.response_payload["proposal"]["title"] == "A Stormy Night"

    body = calls["body"]
    assert body["model"] == "gpt-test"
    assert body["text"]["format"]["strict"] is True
    assert body["store"] is False
    assert "Title: UNKNOWN" in body["input"]
    assert "It was a dark and stormy night." in body["input"]

    # Same source, same declared values: the stage and the call are both reused.
    assert detect_metadata(str(edition.id)).id == run.id
    assert AIRun.objects.count() == 1


def test_provider_failure_keeps_header_metadata_and_finishes_the_stage(
    monkeypatch, settings
) -> None:
    edition = private_edition(title="Header Title", author="Header Author", language="de")
    edition.work.metadata_provenance = {"title": "source", "author": "source", "language": "source"}
    edition.work.save()
    fake_openai(monkeypatch, settings, error=RuntimeError("provider down"))

    run = detect_metadata(str(edition.id))

    edition.refresh_from_db()
    assert run.status == PipelineRun.Status.SUCCEEDED
    assert run.summary["ai_status"] == AIRun.Status.FAILED
    assert edition.work.metadata_detected_at is not None
    assert (edition.title, edition.author) == ("Header Title", "Header Author")
    ai_run = AIRun.objects.get()
    assert ai_run.status == AIRun.Status.FAILED
    assert "provider down" in ai_run.error


def test_unsupported_proposed_language_is_ignored(monkeypatch, settings) -> None:
    edition = private_edition(title="Header Title", author="Header Author", language="de")
    edition.work.metadata_provenance = {"title": "source", "author": "source", "language": "source"}
    edition.work.save()
    fake_openai(
        monkeypatch,
        settings,
        proposal={
            "title": "Header Title",
            "author": "Header Author",
            "language": "tlh",
            "description": "",
            "publication_year": None,
            "note": "",
        },
    )

    detect_metadata(str(edition.id))

    edition.refresh_from_db()
    assert edition.language == "de"
    assert edition.work.metadata_provenance == {
        "title": "source",
        "author": "source",
        "language": "source",
    }


def test_owner_confirmation_updates_fields_and_requeues_nlp_on_language_change(
    monkeypatch,
    settings,
    django_capture_on_commit_callbacks,
) -> None:
    monkeypatch.setenv("ALMONIUM_BOOKS_PUBLISHER_TOKEN", SECRET)
    queued: list[str] = []
    monkeypatch.setattr(
        "almonium_book_processor.catalog.tasks.process_normalized_edition.delay",
        lambda edition_id: queued.append(edition_id),
    )
    edition = private_edition(title="Detected Title", author="Detected Author", language="de")
    edition.work.metadata_provenance = {"title": "ai", "author": "source", "language": "source"}
    edition.work.save()
    client = APIClient()

    with django_capture_on_commit_callbacks(execute=True):
        response = client.put(
            f"/api/v1/internal/imports/{edition.id}/metadata/?owner_id={edition.work.owner_id}",
            {
                "title": "Confirmed Title",
                "author": "Detected Author",
                "description": "The owner's own blurb.",
                "language": "en",
                "publication_year": None,
            },
            format="json",
            HTTP_X_ALMONIUM_BOOKS_TOKEN=SECRET,
        )

    assert response.status_code == 200, response.data
    edition.refresh_from_db()
    assert edition.title == "Confirmed Title"
    assert edition.language == "en"
    assert edition.status == Edition.Status.PROCESSING
    assert edition.work.description == "The owner's own blurb."
    assert edition.work.publication_year is None
    assert edition.work.metadata_provenance == {
        "title": "user",
        "author": "user",
        "description": "user",
        "language": "user",
        "publication_year": "user",
    }
    assert queued == [str(edition.id)]
    assert response.data["metadata"]["provenance"]["language"] == "user"

    # A different owner cannot touch it.
    forbidden = client.put(
        f"/api/v1/internal/imports/{edition.id}/metadata/?owner_id={uuid.uuid4()}",
        {"title": "Hijacked"},
        format="json",
        HTTP_X_ALMONIUM_BOOKS_TOKEN=SECRET,
    )
    assert forbidden.status_code == 404


def test_confirming_the_same_language_does_not_reprocess(monkeypatch) -> None:
    queued: list[str] = []
    monkeypatch.setattr(
        "almonium_book_processor.catalog.tasks.process_normalized_edition.delay",
        lambda edition_id: queued.append(edition_id),
    )
    edition = private_edition(title="Detected Title", author="Detected Author", language="de")

    changed = confirm_metadata(edition, title="Kept", language="de")

    edition.refresh_from_db()
    assert changed is False
    assert edition.status == Edition.Status.READY
    assert edition.title == "Kept"
    assert queued == []


def test_import_event_carries_detected_metadata(monkeypatch) -> None:
    monkeypatch.setenv("ALMONIUM_API_URL", "http://almonium.test/api/v1/")
    monkeypatch.setenv("ALMONIUM_BOOKS_PUBLISHER_TOKEN", SECRET)
    sent: dict = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    def fake_urlopen(request, timeout):
        sent["url"] = request.full_url
        sent["body"] = json.loads(request.data)
        return FakeResponse()

    monkeypatch.setattr("almonium_book_processor.catalog.import_events.urlopen", fake_urlopen)
    edition = private_edition(title="Detected Title", author="Detected Author", language="de")
    edition.work.publication_year = 1912
    edition.work.metadata_provenance = {"title": "ai", "author": "source", "language": "source"}
    edition.work.save()

    send_private_import_event(edition, progress=40)

    assert sent["url"] == "http://almonium.test/api/v1/internal/books/import-events"
    assert sent["body"]["metadata"] == {
        "title": "Detected Title",
        "author": "Detected Author",
        "description": "",
        "language": "de",
        "publicationYear": 1912,
        "provenance": {"title": "ai", "author": "source", "language": "source"},
        "detected": False,
    }


def test_opening_excerpt_is_capped(monkeypatch, settings) -> None:
    from almonium_book_processor.ai.metadata import METADATA_EXCERPT_MAX_CHARS
    from almonium_book_processor.catalog.metadata import opening_excerpt

    edition = private_edition(title="T", author="A", language="en")
    chapter = edition.chapters.get()
    ContentBlock.objects.create(
        edition=edition,
        chapter=chapter,
        block_id="c1.b3",
        sequence=3,
        block_type=ContentBlock.BlockType.PARAGRAPH,
        text="x" * (METADATA_EXCERPT_MAX_CHARS * 2),
    )

    excerpt = opening_excerpt(edition)

    assert excerpt.startswith("Chapter I\n\nIt was a dark and stormy night.")
    assert len(excerpt) == METADATA_EXCERPT_MAX_CHARS
