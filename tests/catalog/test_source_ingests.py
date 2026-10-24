"""The product API asks for a public-domain text by its link on Gutenberg or Wikisource."""

from __future__ import annotations

import io
import uuid
from urllib.error import HTTPError, URLError

import pytest
from celery.exceptions import Retry
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APIClient

from almonium_book_processor.catalog import source_download, tasks
from almonium_book_processor.catalog.models import Edition, SourceDownload, Work
from almonium_book_processor.catalog.source_download import (
    MAX_BYTES,
    USER_AGENT,
    DownloadRefused,
    check_download_url,
)

pytestmark = pytest.mark.django_db

SECRET = "test-shared-secret"
HEADERS = {"HTTP_X_ALMONIUM_BOOKS_SECRET": SECRET}
ENDPOINT = "/api/v1/internal/source-ingests/"
GUTENBERG_EPUB = "https://www.gutenberg.org/ebooks/84.epub3.images"
GUTENBERG_CACHE = "https://www.gutenberg.org/cache/epub/84/pg84-images-3.epub"
EXPORT = "https://ws-export.wmcloud.org/?lang=fr&page=Guerre_et_Paix&format=epub-3"
# over MIN_BYTES: a smaller file is refused as an audiobook's track list
EPUB_BYTES = b"PK\x03\x04" + b"epub body" * 3_000


@pytest.fixture(autouse=True)
def shared_secret(monkeypatch, settings, tmp_path):
    monkeypatch.setenv("ALMONIUM_BOOKS_PUBLISHER_SECRET", SECRET)
    settings.MEDIA_ROOT = tmp_path


@pytest.fixture
def queued(monkeypatch):
    """The tasks queued by commit callbacks, instead of a broker."""

    log: list[tuple[str, str]] = []
    monkeypatch.setattr(
        tasks.download_source_edition,
        "delay",
        lambda edition_id: log.append(("download", edition_id)),
    )
    monkeypatch.setattr(
        tasks.process_book_pipeline,
        "delay",
        lambda edition_id: log.append(("pipeline", edition_id)),
    )
    return log


def body(**overrides) -> dict:
    return {
        "external_id": str(uuid.uuid4()),
        "download_url": GUTENBERG_EPUB,
        "source_kind": "gutenberg",
        "source_page_url": "https://www.gutenberg.org/ebooks/84",
        "title": "Frankenstein",
        "author": "Mary Shelley",
        "language": "en",
        "publication_year": 1818,
        **overrides,
    }


class FakeResponse:
    def __init__(self, data: bytes, headers: dict | None = None) -> None:
        self._stream = io.BytesIO(data)
        self.headers = {"Content-Type": "application/epub+zip", **(headers or {})}

    def read(self, size: int = -1) -> bytes:
        return self._stream.read(size)

    def __enter__(self):
        return self

    def __exit__(self, *exc) -> None:
        return None


def http_error(url: str, code: int, headers: dict | None = None) -> HTTPError:
    return HTTPError(url, code, "status", headers or {}, io.BytesIO(b""))


def fake_web(monkeypatch, routes: dict[str, object]) -> list:
    """Answer each URL from ``routes``: a response, or an exception to raise."""

    seen: list = []

    def urlopen(request, timeout):
        seen.append(request)
        # an address nobody routed does not exist, as on the web
        answer = routes.get(request.full_url) or http_error(request.full_url, 404)
        if isinstance(answer, Exception):
            raise answer
        return answer

    monkeypatch.setattr(source_download, "_open", urlopen)
    return seen


def create(**overrides) -> Edition:
    response = APIClient().post(ENDPOINT, body(**overrides), format="json", **HEADERS)
    assert response.status_code == 202, response.content
    return Edition.objects.select_related("source_download").get(id=response.json()["edition_id"])


# --- the request -------------------------------------------------------------


@pytest.mark.parametrize(
    ("overrides", "field"),
    [
        ({"download_url": "http://www.gutenberg.org/ebooks/84.epub3.images"}, "download_url"),
        ({"download_url": "https://evil.example/ebooks/84.epub3.images"}, "download_url"),
        (
            {"download_url": "https://www.gutenberg.org.evil.example/ebooks/84.epub3.images"},
            "download_url",
        ),
        ({"download_url": "https://www.gutenberg.org:8443/ebooks/84.epub3.images"}, "download_url"),
        ({"download_url": "https://user@www.gutenberg.org/ebooks/84.epub3.images"}, "download_url"),
        ({"download_url": "https://www.gutenberg.org/ebooks/84"}, "download_url"),
        ({"download_url": "https://www.gutenberg.org/ebooks/84.txt.utf-8"}, "download_url"),
        (
            {"download_url": "https://www.gutenberg.org/cache/epub/84/pg85-images-3.epub"},
            "download_url",
        ),
        # The kind and the host must agree.
        ({"download_url": EXPORT}, "download_url"),
        ({"source_kind": "wikisource", "download_url": GUTENBERG_EPUB}, "download_url"),
        (
            {
                "source_kind": "wikisource",
                "download_url": "https://ws-export.wmcloud.org/?lang=fr&page=X&format=pdf-a4",
                "source_page_url": "https://fr.wikisource.org/wiki/X",
            },
            "download_url",
        ),
        (
            {
                "source_kind": "wikisource",
                "download_url": "https://ws-export.wmcloud.org/?format=epub-3",
                "source_page_url": "https://fr.wikisource.org/wiki/X",
            },
            "download_url",
        ),
        ({"source_page_url": "https://evil.example/ebooks/84"}, "source_page_url"),
        ({"source_kind": "archive"}, "source_kind"),
        ({"language": "xx-not-a-language"}, "language"),
    ],
)
def test_a_link_off_the_allowlist_is_refused(overrides, field) -> None:
    response = APIClient().post(ENDPOINT, body(**overrides), format="json", **HEADERS)

    assert response.status_code == 400
    assert field in response.json()
    assert not Edition.objects.exists()


@pytest.mark.parametrize(
    ("url", "kind"),
    [
        (GUTENBERG_EPUB, "gutenberg"),
        ("https://gutenberg.org/ebooks/2600.epub.noimages", "gutenberg"),
        ("https://www.gutenberg.org/ebooks/2600.epub.images", "gutenberg"),
        (GUTENBERG_CACHE, "gutenberg"),
        ("https://www.gutenberg.org/cache/epub/84/pg84.epub", "gutenberg"),
        (EXPORT, "wikisource"),
        ("https://ws-export.wmcloud.org/?lang=en&page=The_Time_Machine&format=epub", "wikisource"),
    ],
)
def test_the_approved_links_pass(url, kind) -> None:
    check_download_url(url, kind)


def test_the_service_token_is_required() -> None:
    response = APIClient().post(ENDPOINT, body(), format="json")

    assert response.status_code in (401, 403)
    assert not Edition.objects.exists()


def test_a_request_makes_a_public_edition_that_waits_for_its_download(
    queued, django_capture_on_commit_callbacks
) -> None:
    request = body(
        source_kind="wikisource",
        download_url=EXPORT,
        source_page_url="https://fr.wikisource.org/wiki/Guerre_et_Paix",
        title="Guerre et Paix",
        author="Léon Tolstoï",
        language="fr",
        publication_year=None,
    )
    client = APIClient()

    with django_capture_on_commit_callbacks(execute=True):
        first = client.post(ENDPOINT, request, format="json", **HEADERS)

    assert first.status_code == 202, first.content
    payload = first.json()
    edition = Edition.objects.select_related("work", "source_download").get(
        id=payload["edition_id"]
    )
    assert payload == {
        "edition_id": str(edition.id),
        "slug": edition.slug,
        "status": "queued",
        "phase": "downloading",
        "progress": 0,
        "error": "",
        "published_at": None,
        "published_book_id": None,
        "completed_stages": [],
        "current_stage": None,
    }
    assert edition.work.visibility == Work.Visibility.PUBLIC
    assert edition.work.title == "Guerre et Paix"
    assert edition.author == "Léon Tolstoï"
    assert edition.language == "fr"
    assert edition.external_job_id == uuid.UUID(request["external_id"])
    assert not edition.source_file
    record = edition.source_download
    assert (record.source_kind, record.download_url, record.source_page_url) == (
        "wikisource",
        EXPORT,
        "https://fr.wikisource.org/wiki/Guerre_et_Paix",
    )
    assert record.status == SourceDownload.Status.PENDING
    assert queued == [("download", str(edition.id))]

    # The same id again is the same edition, whatever else the body says.
    second = client.post(ENDPOINT, {**request, "title": "Something else"}, format="json", **HEADERS)
    assert second.status_code == 200
    assert second.json()["edition_id"] == str(edition.id)
    assert Edition.objects.count() == 1

    detail = client.get(f"{ENDPOINT}{edition.id}/", **HEADERS)
    assert detail.status_code == 200
    assert detail.json() == payload


def test_an_id_that_names_another_job_is_a_conflict() -> None:
    work = Work.objects.create(slug="other", title="Other", author="A", original_language="en")
    taken = uuid.uuid4()
    Edition.objects.create(
        slug="other-en", work=work, title="Other", author="A", language="en", external_job_id=taken
    )

    response = APIClient().post(ENDPOINT, body(external_id=str(taken)), format="json", **HEADERS)

    assert response.status_code == 409
    assert Edition.objects.count() == 1


def test_the_detail_serves_only_source_ingests() -> None:
    work = Work.objects.create(slug="other", title="Other", author="A", original_language="en")
    upload = Edition.objects.create(
        slug="other-en", work=work, title="Other", author="A", language="en"
    )

    response = APIClient().get(f"{ENDPOINT}{upload.id}/", **HEADERS)

    assert response.status_code == 404


# --- the download --------------------------------------------------------------


def test_the_worker_follows_the_redirect_attaches_the_file_and_starts_the_pipeline(
    monkeypatch, queued, django_capture_on_commit_callbacks
) -> None:
    edition = create()
    seen = fake_web(
        monkeypatch,
        {
            GUTENBERG_EPUB: http_error(GUTENBERG_EPUB, 302, {"Location": GUTENBERG_CACHE}),
            GUTENBERG_CACHE: FakeResponse(EPUB_BYTES, {"Content-Length": str(len(EPUB_BYTES))}),
        },
    )

    with django_capture_on_commit_callbacks(execute=True):
        tasks.download_source_edition.run(str(edition.id))

    assert [request.full_url for request in seen] == [GUTENBERG_EPUB, GUTENBERG_CACHE]
    assert all(request.get_header("User-agent") == USER_AGENT for request in seen)
    edition.refresh_from_db()
    record = edition.source_download
    record.refresh_from_db()
    with edition.source_file.open("rb") as stored:
        assert stored.read() == EPUB_BYTES
    assert edition.source_file.name.endswith(".epub")
    assert record.status == SourceDownload.Status.DOWNLOADED
    assert record.final_url == GUTENBERG_CACHE
    assert record.size_bytes == len(EPUB_BYTES)
    assert record.attempts == 1
    assert record.downloaded_at is not None
    assert queued == [("pipeline", str(edition.id))]

    status = APIClient().get(f"{ENDPOINT}{edition.id}/", **HEADERS).json()
    assert status["phase"] == "ingesting"

    # A second delivery of the same message does nothing.
    tasks.download_source_edition.run(str(edition.id))
    assert len(seen) == 2


@pytest.mark.parametrize(
    ("answer", "reason"),
    [
        (
            http_error(GUTENBERG_EPUB, 302, {"Location": "https://evil.example/x.epub"}),
            "redirected off the approved hosts",
        ),
        (
            http_error(GUTENBERG_EPUB, 302, {"Location": "http://www.gutenberg.org/x.epub"}),
            "redirected off the approved hosts",
        ),
        (http_error(GUTENBERG_EPUB, 404), "HTTP 404"),
        (FakeResponse(b"<html>Not here</html>", {"Content-Type": "text/html"}), "not an EPUB"),
        (FakeResponse(EPUB_BYTES, {"Content-Length": str(MAX_BYTES + 1)}), "limit is 60 MB"),
    ],
)
def test_a_download_that_cannot_become_a_book_fails_the_edition(
    monkeypatch, queued, answer, reason
) -> None:
    edition = create()
    fake_web(monkeypatch, {GUTENBERG_EPUB: answer})

    tasks.download_source_edition.run(str(edition.id))

    edition.refresh_from_db()
    assert edition.status == Edition.Status.FAILED
    assert not edition.source_file
    assert edition.source_download.status == SourceDownload.Status.FAILED
    assert reason in edition.source_download.error
    status = APIClient().get(f"{ENDPOINT}{edition.id}/", **HEADERS).json()
    assert status["phase"] == "failed"
    assert reason in status["error"]
    assert queued == []


def test_a_stream_over_the_cap_is_cut_off(monkeypatch) -> None:
    monkeypatch.setattr(source_download, "MAX_BYTES", 1000)
    fake_web(monkeypatch, {GUTENBERG_EPUB: FakeResponse(b"PK\x03\x04" + b"x" * 2000)})

    with pytest.raises(DownloadRefused, match="over the"):
        source_download.download(GUTENBERG_EPUB, "gutenberg")


def test_an_audiobook_stub_is_refused_as_too_small(monkeypatch) -> None:
    # Gutenberg 19790, Der Schimmelreiter read aloud: a 10 KB EPUB holding the track list
    fake_web(monkeypatch, {GUTENBERG_EPUB: FakeResponse(b"PK\x03\x04" + b"x" * 10_000)})

    with pytest.raises(DownloadRefused, match="too small"):
        source_download.download(GUTENBERG_EPUB, "gutenberg")


def test_a_library_that_is_down_is_tried_again_then_given_up_on(monkeypatch, queued) -> None:
    edition = create()
    fake_web(monkeypatch, {GUTENBERG_EPUB: http_error(GUTENBERG_EPUB, 503)})

    with pytest.raises(Retry):
        tasks.download_source_edition.run(str(edition.id))

    edition.refresh_from_db()
    edition.source_download.refresh_from_db()
    assert edition.status == Edition.Status.QUEUED
    assert edition.source_download.status == SourceDownload.Status.PENDING
    assert "HTTP 503" in edition.source_download.error
    assert APIClient().get(f"{ENDPOINT}{edition.id}/", **HEADERS).json()["phase"] == ("downloading")

    fake_web(monkeypatch, {GUTENBERG_EPUB: URLError(TimeoutError("timed out"))})
    tasks.download_source_edition.push_request(retries=tasks.DOWNLOAD_RETRIES)
    try:
        tasks.download_source_edition.run(str(edition.id))
    finally:
        tasks.download_source_edition.pop_request()

    edition.refresh_from_db()
    edition.source_download.refresh_from_db()
    assert edition.status == Edition.Status.FAILED
    assert "could not be reached" in edition.source_download.error
    assert "Gave up after 2 tries" in edition.source_download.error


# --- the edition page ----------------------------------------------------------


@pytest.fixture
def staff_client():
    user = get_user_model().objects.create_user("editor", "editor@example.test", "pw")
    user.is_staff = True
    user.save(update_fields=["is_staff"])
    client = APIClient()
    client.force_login(user)
    return client


def test_the_edition_page_shows_where_the_text_came_from(staff_client, queued) -> None:
    edition = create()

    page = staff_client.get(reverse("catalog:edition-detail", args=[edition.id])).content.decode()

    assert "https://www.gutenberg.org/ebooks/84" in page
    assert "Project Gutenberg" in page
    assert "Downloading the text from Project Gutenberg" in page


def test_a_failed_download_is_retried_from_the_edition_page(
    monkeypatch, staff_client, queued, django_capture_on_commit_callbacks
) -> None:
    edition = create()
    fake_web(monkeypatch, {GUTENBERG_EPUB: http_error(GUTENBERG_EPUB, 404)})
    tasks.download_source_edition.run(str(edition.id))
    page = staff_client.get(reverse("catalog:edition-detail", args=[edition.id])).content.decode()
    assert "The download failed" in page

    with django_capture_on_commit_callbacks(execute=True):
        staff_client.post(reverse("catalog:retry-edition", args=[edition.id]))

    edition.refresh_from_db()
    edition.source_download.refresh_from_db()
    assert edition.status == Edition.Status.QUEUED
    assert edition.source_download.status == SourceDownload.Status.PENDING
    assert edition.source_download.error == ""
    assert queued[-1] == ("download", str(edition.id))


def test_a_gutenberg_book_without_the_images_build_is_fetched_in_its_plain_build(monkeypatch):
    plain = "https://www.gutenberg.org/ebooks/84.epub.noimages"
    seen = fake_web(monkeypatch, {plain: FakeResponse(EPUB_BYTES)})

    fetched = source_download.download(GUTENBERG_EPUB, "gutenberg")

    assert fetched.final_url == plain and fetched.size == len(EPUB_BYTES)
    assert [request.full_url.rsplit(".", 2)[-2:] for request in seen] == [
        ["epub3", "images"],
        ["epub", "images"],
        ["epub", "noimages"],
    ]
    fetched.path.unlink()


def test_a_gutenberg_book_with_no_epub_at_all_is_refused_as_before(monkeypatch):
    fake_web(monkeypatch, {})

    with pytest.raises(source_download.DownloadRefused, match="HTTP 404"):
        source_download.download(GUTENBERG_EPUB, "gutenberg")


def test_a_gutenberg_images_build_too_large_for_its_pictures_falls_back_to_the_plain_build(
    monkeypatch,
):
    plain = "https://www.gutenberg.org/ebooks/84.epub.noimages"
    seen = fake_web(
        monkeypatch,
        {
            GUTENBERG_EPUB: FakeResponse(EPUB_BYTES, {"Content-Length": str(82 * 1024 * 1024)}),
            plain: FakeResponse(EPUB_BYTES),
        },
    )

    fetched = source_download.download(GUTENBERG_EPUB, "gutenberg")

    assert fetched.final_url == plain
    assert len(seen) == 3
    fetched.path.unlink()
