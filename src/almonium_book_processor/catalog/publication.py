from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from almonium_book_processor.catalog.models import Edition


class PublicationError(RuntimeError):
    pass


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
        with urlopen(request, timeout=30) as response:  # noqa: S310 - configured service endpoint
            return json.loads(response.read())
    except HTTPError as error:
        raise PublicationError(f"{failure} with HTTP {error.code}.") from error
    except (URLError, TimeoutError, json.JSONDecodeError) as error:
        raise PublicationError(f"{failure}.") from error


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
        "description": edition.work.description,
        "originalLanguage": edition.work.original_language.upper(),
        "language": edition.language.upper(),
        "editionType": edition.edition_type,
        "sourceEditionSlug": edition.source_edition.slug if edition.source_edition else None,
        "translator": edition.translator or None,
        "publicationYear": edition.work.publication_year,
        "coverUrl": edition.work.cover_url or None,
        "cefrLevel": edition.cefr_level,
        "wordCount": edition.word_count,
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
