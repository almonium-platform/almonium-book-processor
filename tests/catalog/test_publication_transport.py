from __future__ import annotations

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
