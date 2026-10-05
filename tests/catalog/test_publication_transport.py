from __future__ import annotations

import hashlib
import hmac
import io
import json
from urllib.error import HTTPError, URLError

import pytest

from almonium_book_processor.catalog import publication


@pytest.fixture(autouse=True)
def configured_api(monkeypatch):
    monkeypatch.setenv("ALMONIUM_API_URL", "http://api.example.test:9998")
    monkeypatch.setenv("ALMONIUM_BOOKS_PUBLISHER_TOKEN", "test-shared-secret")


def test_a_refused_connection_names_the_host_and_the_reason(monkeypatch):
    def refuse(request, timeout=None):
        raise URLError(ConnectionRefusedError(111, "Connection refused"))

    monkeypatch.setattr(publication, "urlopen", refuse)

    with pytest.raises(publication.PublicationError) as failure:
        publication._signed_post("/internal/books/publications", {}, failure="Publication failed")

    assert str(failure.value) == (
        "Publication failed: api.example.test:9998: [Errno 111] Connection refused."
    )


def _http_error(code: int, body: bytes) -> HTTPError:
    return HTTPError("http://api.example.test:9998/x", code, "", {}, io.BytesIO(body))


def test_a_refusal_quotes_the_api_message(monkeypatch):
    body = json.dumps(
        {"success": False, "message": "Invalid publication request: sourceHash must not be blank"}
    ).encode()
    monkeypatch.setattr(
        publication,
        "urlopen",
        lambda request, timeout=None: (_ for _ in ()).throw(_http_error(400, body)),
    )

    with pytest.raises(publication.PublicationError) as failure:
        publication._signed_post("/internal/books/publications", {}, failure="Publication failed")

    assert str(failure.value) == (
        "Publication failed with HTTP 400 "
        "(Invalid publication request: sourceHash must not be blank)."
    )


def test_a_refusal_without_a_body_keeps_the_status_only(monkeypatch):
    monkeypatch.setattr(
        publication,
        "urlopen",
        lambda request, timeout=None: (_ for _ in ()).throw(_http_error(500, b"")),
    )

    with pytest.raises(publication.PublicationError) as failure:
        publication._signed_post("/internal/books/publications", {}, failure="Publication failed")

    assert str(failure.value) == "Publication failed with HTTP 500."


def test_a_timeout_says_so_in_seconds(monkeypatch):
    def hang(request, timeout=None):
        raise URLError(TimeoutError("timed out"))

    monkeypatch.setattr(publication, "urlopen", hang)

    with pytest.raises(publication.PublicationError, match="did not answer within 30s"):
        publication._signed_post("/internal/books/publications", {}, failure="Publication failed")


def test_the_socket_opens_on_the_connect_timeout_then_waits_the_read_timeout(monkeypatch):
    seen: dict[str, float] = {}

    class FakeSocket:
        def setsockopt(self, *args):
            pass

        def settimeout(self, value):
            seen["read"] = value

    def fake_create_connection(address, timeout, source_address=None, **_):
        seen["connect"] = timeout
        return FakeSocket()

    monkeypatch.setattr("http.client.socket.create_connection", fake_create_connection)

    connection = publication._TimedConnection("api.example.test", 9998, timeout=30)
    connection.connect()

    assert seen == {"connect": publication.CONNECT_TIMEOUT_SECONDS, "read": 30}


def test_a_conflict_is_a_refusal_carrying_the_apis_reason_whole(monkeypatch):
    reason = "Under copyright in UA and DE until the end of 2046 (by the catalogue's dates)."
    body = json.dumps({"success": False, "message": reason}).encode()
    monkeypatch.setattr(
        publication,
        "urlopen",
        lambda request, timeout=None: (_ for _ in ()).throw(_http_error(409, body)),
    )

    with pytest.raises(publication.PublicationRefused) as refusal:
        publication._signed_post("/internal/books/publications", {}, failure="Publication failed")

    assert refusal.value.reason == reason
    assert str(refusal.value) == f"Refused by Almonium: {reason}"
    assert isinstance(refusal.value, publication.PublicationError)


class _Answer(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _source_edition():
    from almonium_book_processor.catalog.models import Edition, Work

    work = Work.objects.create(
        slug="dead-souls", title="Dead Souls", author="Nikolai Gogol", publication_year=1842
    )
    return Edition.objects.create(
        work=work, slug="dead-souls-ru", title="Dead Souls", author="Nikolai Gogol", language="ru"
    )


@pytest.mark.django_db
def test_the_rights_check_is_signed_like_a_publication_and_its_answer_read(monkeypatch):
    seen = {}

    def answer(request, timeout=None):
        seen["request"] = request
        return _Answer(
            json.dumps(
                {
                    "status": "FREE",
                    "freeFrom": 1923,
                    "countries": ["UA", "DE"],
                    "catalogWorkId": "6c1f0e9a-3b43-4c55-8f0e-2d6f6f9f1a11",
                    "catalogTitle": "Dead Souls",
                    "catalogAuthor": "Nikolai Gogol",
                    "explanation": "Free in UA and DE since 1923.",
                }
            ).encode()
        )

    monkeypatch.setattr(publication, "urlopen", answer)

    verdict = publication.check_rights(_source_edition())

    request = seen["request"]
    assert request.full_url == (
        "http://api.example.test:9998/internal/books/publications/rights-check"
    )
    assert json.loads(request.data) == {
        "workSlug": "dead-souls",
        "title": "Dead Souls",
        "author": "Nikolai Gogol",
        "publicationYear": 1842,
    }
    timestamp = request.get_header("X-almonium-books-timestamp")
    expected = hmac.new(
        b"test-shared-secret", f"{timestamp}.".encode() + request.data, hashlib.sha256
    ).hexdigest()
    assert request.get_header("X-almonium-books-signature") == expected
    assert verdict == publication.RightsVerdict(
        status="FREE",
        explanation="Free in UA and DE since 1923.",
        free_from=1923,
        countries=["UA", "DE"],
        catalog_work_id="6c1f0e9a-3b43-4c55-8f0e-2d6f6f9f1a11",
        catalog_title="Dead Souls",
        catalog_author="Nikolai Gogol",
    )


@pytest.mark.django_db
def test_a_rights_check_that_cannot_be_made_is_unchecked_not_an_error(monkeypatch):
    def refuse(request, timeout=None):
        raise URLError(ConnectionRefusedError(111, "Connection refused"))

    monkeypatch.setattr(publication, "urlopen", refuse)

    verdict = publication.check_rights(_source_edition())

    assert verdict.status == publication.RIGHTS_UNCHECKED
    assert verdict.explanation == (
        "Almonium rights check failed: api.example.test:9998: [Errno 111] Connection refused."
    )


@pytest.mark.django_db
def test_an_unconfigured_api_or_an_unreadable_answer_leaves_the_rights_unchecked(monkeypatch):
    edition = _source_edition()
    monkeypatch.setattr(publication, "urlopen", lambda request, timeout=None: _Answer(b"{}"))

    assert publication.check_rights(edition).status == publication.RIGHTS_UNCHECKED

    monkeypatch.delenv("ALMONIUM_API_URL")
    verdict = publication.check_rights(edition)

    assert verdict.status == publication.RIGHTS_UNCHECKED
    assert "not configured" in verdict.explanation
