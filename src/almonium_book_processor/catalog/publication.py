from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
from http.client import HTTPConnection, HTTPSConnection
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPHandler, HTTPSHandler, Request, build_opener

from almonium_book_processor.catalog.adaptation_floor import reached_levels
from almonium_book_processor.catalog.models import Edition

# A product API that is up answers a publication in well under a second, so a
# connection that cannot even be opened quickly is a dead or unreachable host,
# and the editor should hear that in seconds rather than after a full read
# timeout.
CONNECT_TIMEOUT_SECONDS = 5
READ_TIMEOUT_SECONDS = 30


class PublicationError(RuntimeError):
    pass


class _TimedConnection(HTTPConnection):
    """Open the socket within the connect timeout, then wait the read timeout."""

    def connect(self) -> None:
        read_timeout, self.timeout = self.timeout, CONNECT_TIMEOUT_SECONDS
        super().connect()
        self.sock.settimeout(read_timeout)


class _TimedHTTPSConnection(_TimedConnection, HTTPSConnection):
    pass


class _TimedHTTPHandler(HTTPHandler):
    def http_open(self, req):
        return self.do_open(_TimedConnection, req)


class _TimedHTTPSHandler(HTTPSHandler):
    def https_open(self, req):
        return self.do_open(_TimedHTTPSConnection, req, context=self._context)


urlopen = build_opener(_TimedHTTPHandler, _TimedHTTPSHandler).open


def _describe(error: Exception, url: str, timeout: int = READ_TIMEOUT_SECONDS) -> str:
    """Say what went wrong on the wire, so a firewall reads differently from a crash."""

    reason = getattr(error, "reason", error)
    host = urlsplit(url).netloc
    if isinstance(reason, TimeoutError):
        return f"{host} did not answer within {timeout}s"
    return f"{host}: {reason}"


def _response_reason(error: HTTPError) -> str:
    """Return the API's own explanation of a refusal, if it sent one."""

    try:
        body = error.read().decode("utf-8", errors="replace")
    except OSError:
        return ""
    try:
        parsed = json.loads(body)
    except json.JSONDecodeError:
        return body.strip()[:300]
    if isinstance(parsed, dict):
        message = parsed.get("message") or parsed.get("error") or ""
        return str(message).strip()[:300]
    return ""


def _signed_post(path: str, payload: dict[str, Any], *, failure: str) -> Any:
    """POST a signed body to the product API's internal books surface."""

    api_url = os.getenv("ALMONIUM_API_URL", "").rstrip("/")
    token = os.getenv("ALMONIUM_BOOKS_PUBLISHER_TOKEN", "")
    if not api_url or not token:
        raise PublicationError("Almonium publication is not configured.")
    request_body = json.dumps(payload, separators=(",", ":")).encode()
    timestamp = str(int(time.time()))
    signature = hmac.new(
        token.encode(),
        f"{timestamp}.".encode() + request_body,
        hashlib.sha256,
    ).hexdigest()
    request = Request(
        f"{api_url}{path}",
        data=request_body,
        headers={
            "Content-Type": "application/json",
            "X-Almonium-Books-Timestamp": timestamp,
            "X-Almonium-Books-Signature": signature,
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=READ_TIMEOUT_SECONDS) as response:  # noqa: S310
            return json.loads(response.read())
    except HTTPError as error:
        reason = _response_reason(error)
        detail = f" ({reason})" if reason else ""
        raise PublicationError(f"{failure} with HTTP {error.code}{detail}.") from error
    except (URLError, TimeoutError) as error:
        raise PublicationError(f"{failure}: {_describe(error, request.full_url)}.") from error
    except json.JSONDecodeError as error:
        raise PublicationError(f"{failure}: Almonium returned a non-JSON body.") from error


def withdraw_from_almonium(edition: Edition) -> bool:
    """Ask the product API to stop serving this edition.

    Returns whether a published book was actually withdrawn: an edition the API
    does not know is already as withdrawn as it can be, and saying so lets a
    retried takedown finish instead of stalling.
    """

    response_payload = _signed_post(
        "/internal/books/publications/withdrawals",
        {"editionSlug": edition.slug},
        failure="Almonium withdrawal failed",
    )
    try:
        return bool(response_payload["withdrawn"])
    except (KeyError, TypeError) as error:
        raise PublicationError("Almonium returned an invalid withdrawal response.") from error


def publish_to_almonium(edition: Edition) -> str:
    """Send a versioned, explicit publication request to the product API."""
    payload: dict[str, Any] = {
        "editionSlug": edition.slug,
        "sourceHash": edition.source_sha256,
        "workSlug": edition.work.slug,
        "title": edition.title,
        "author": edition.author,
        "description": edition.public_description,
        "originalLanguage": edition.work.original_language.upper(),
        "language": edition.language.upper(),
        "editionType": edition.edition_type,
        "literaryRegister": edition.literary_register or None,
        "sourceEditionSlug": edition.source_edition.slug if edition.source_edition else None,
        "translator": edition.translator or None,
        "publicationYear": edition.work.publication_year,
        "coverUrl": edition.work.cover_url or None,
        "cefrLevel": edition.cefr_level,
        # The work's adaptation floor and the levels it has gate-passing
        # editions at: found per book from pilot evidence, never promised.
        "adaptsTo": edition.work.adapts_to,
        "reachedLevels": reached_levels(edition.work),
        "wordCount": edition.word_count,
        # What every shelf says "chapter 3 of 24" against; the processor is its one source.
        "chapterCount": edition.chapters.count(),
        "editionId": str(edition.id),
        "externalJobId": str(edition.external_job_id) if edition.external_job_id else None,
    }
    response_payload = _signed_post(
        "/internal/books/publications",
        payload,
        failure="Almonium publication failed",
    )
    try:
        return str(response_payload["bookId"])
    except (KeyError, TypeError) as error:
        raise PublicationError("Almonium returned an invalid publication response.") from error
