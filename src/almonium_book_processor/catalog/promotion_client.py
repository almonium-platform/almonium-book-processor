"""Pushing an edition bundle to another deployment of this service.

The source pushes, because a laptop is not reachable from the server while
every deployed processor has a public host. The token is one a staff account
issued on the target, so the target's own admin decides who may write to it.
"""

from __future__ import annotations

import json
import uuid
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request

from almonium_book_processor.catalog.models import PromotionTarget
from almonium_book_processor.catalog.promotion import PromotionError
from almonium_book_processor.catalog.publication import _describe, _response_reason, urlopen

CAPABILITIES_PATH = "/api/v1/internal/promotions/capabilities/"
IMPORT_PATH = "/api/v1/internal/promotions/"
# A small answer about what the target runs; and a whole edition landing in
# one transaction, which stays under the target's request timeout.
CAPABILITIES_TIMEOUT_SECONDS = 15
IMPORT_TIMEOUT_SECONDS = 110


def _multipart(fields: dict[str, str], file_name: str, file_data: bytes) -> tuple[bytes, str]:
    boundary = uuid.uuid4().hex
    body = bytearray()
    for name, value in fields.items():
        body += (
            f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'
        ).encode()
    body += (
        f'--{boundary}\r\nContent-Disposition: form-data; name="bundle"; '
        f'filename="{file_name}"\r\nContent-Type: application/zip\r\n\r\n'
    ).encode()
    body += file_data + f"\r\n--{boundary}--\r\n".encode()
    return bytes(body), f"multipart/form-data; boundary={boundary}"


class PromotionClient:
    def __init__(self, target: PromotionTarget):
        self.target = target
        self.base_url = target.base_url.rstrip("/")

    def _request(self, request: Request, *, timeout: int, failure: str) -> Any:
        request.add_header("Authorization", f"Token {self.target.token}")
        request.add_header("Accept", "application/json")
        try:
            with urlopen(request, timeout=timeout) as response:  # noqa: S310
                return json.loads(response.read())
        except HTTPError as error:
            if error.code == 404:
                raise PromotionError(
                    f"{failure}: {self.target.name} does not run a build with promotion "
                    "support yet (HTTP 404)."
                ) from error
            if error.code in {401, 403}:
                raise PromotionError(
                    f"{failure}: {self.target.name} rejected the token (HTTP {error.code})."
                ) from error
            reason = _response_reason(error)
            detail = f" ({reason})" if reason else ""
            raise PromotionError(f"{failure} with HTTP {error.code}{detail}.") from error
        except (URLError, TimeoutError) as error:
            raise PromotionError(
                f"{failure}: {_describe(error, request.full_url, timeout)}."
            ) from error
        except json.JSONDecodeError as error:
            raise PromotionError(
                f"{failure}: {self.target.name} returned a non-JSON body."
            ) from error

    def capabilities(self, slugs: list[str]) -> dict[str, Any]:
        query = urlencode([("slug", slug) for slug in slugs])
        request = Request(f"{self.base_url}{CAPABILITIES_PATH}?{query}", method="GET")
        return self._request(
            request,
            timeout=CAPABILITIES_TIMEOUT_SECONDS,
            failure=f"Could not ask {self.target.name} what it runs",
        )

    def push(self, bundle: bytes, *, file_name: str, publish: bool) -> dict[str, Any]:
        body, content_type = _multipart(
            {"publish": "true" if publish else "false"}, file_name, bundle
        )
        request = Request(
            f"{self.base_url}{IMPORT_PATH}",
            data=body,
            headers={"Content-Type": content_type},
            method="POST",
        )
        return self._request(
            request,
            timeout=IMPORT_TIMEOUT_SECONDS,
            failure=f"Promotion to {self.target.name} failed",
        )
