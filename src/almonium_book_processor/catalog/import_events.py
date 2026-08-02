from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
from urllib.request import Request, urlopen

from almonium_book_processor.catalog.models import Edition


def send_private_import_event(
    edition: Edition,
    *,
    progress: int,
    error: str | None = None,
) -> None:
    """Report private-import progress; callback delivery must not fail ingestion."""
    api_url = os.getenv("ALMONIUM_API_URL", "").rstrip("/")
    token = os.getenv("ALMONIUM_BOOKS_PUBLISHER_TOKEN", "")
    if not api_url or not token or edition.work.owner_id is None:
        return

    payload = {
        "importId": str(edition.id),
        "ownerId": str(edition.work.owner_id),
        "status": edition.status,
        "title": edition.title,
        "progress": progress,
        "wordCount": edition.word_count,
        "error": error or None,
    }
    body = json.dumps(payload, separators=(",", ":")).encode()
    timestamp = str(int(time.time()))
    signature = hmac.new(
        token.encode(),
        f"{timestamp}.".encode() + body,
        hashlib.sha256,
    ).hexdigest()
    request = Request(
        f"{api_url}/internal/books/import-events",
        data=body,
        headers={
            "Content-Type": "application/json",
            "X-Almonium-Books-Timestamp": timestamp,
            "X-Almonium-Books-Signature": signature,
        },
        method="POST",
    )
    with urlopen(request, timeout=10):  # noqa: S310 - configured service endpoint
        pass
