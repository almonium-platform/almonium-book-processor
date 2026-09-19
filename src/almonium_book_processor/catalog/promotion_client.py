"""Moving edition bundles between deployments of this service over HTTP.

A laptop pushes to staging, because it is not reachable from the server while
every deployed processor has a public host; for the same reason it pulls from
staging rather than being pushed to. Both directions use the token the deployed
side was given, so the infrastructure decides who may write to or read from it.
"""

from __future__ import annotations

import json
import uuid
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request

from almonium_book_processor.catalog.promotion import PromotionError, PromotionTarget
from almonium_book_processor.catalog.publication import _describe, _response_reason, urlopen

TOKEN_HEADER = "X-Almonium-Books-Promotion-Token"
CAPABILITIES_PATH = "/api/v1/internal/promotions/capabilities/"
IMPORT_PATH = "/api/v1/internal/promotions/"
EXPORTS_PATH = "/api/v1/internal/promotions/exports/"
# A small answer about what the target runs; and a whole edition landing in
# one transaction, or being bundled, which stays under the request timeout.
CAPABILITIES_TIMEOUT_SECONDS = 15
IMPORT_TIMEOUT_SECONDS = 110
EXPORT_TIMEOUT_SECONDS = 110


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


def _json_message(error: HTTPError) -> str:
    try:
        parsed = json.loads(error.read())
    except (OSError, ValueError):
        return ""
    return str(parsed.get("message") or "") if isinstance(parsed, dict) else ""


class PromotionClient:
    def __init__(self, target: PromotionTarget):
        self.target = target
        self.base_url = target.base_url.rstrip("/")

    def _fetch(self, request: Request, *, timeout: int, failure: str, accept: str) -> bytes:
        request.add_header(TOKEN_HEADER, self.target.token)
        request.add_header("Accept", accept)
        try:
            with urlopen(request, timeout=timeout) as response:  # noqa: S310
                return response.read()
        except HTTPError as error:
            if error.code == 404:
                # The endpoint answers 404 in JSON for a slug it does not have;
                # a build without the endpoint answers with Django's page.
                message = _json_message(error)
                if message:
                    raise PromotionError(f"{failure}: {message}") from error
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

    def _request(self, request: Request, *, timeout: int, failure: str) -> Any:
        body = self._fetch(request, timeout=timeout, failure=failure, accept="application/json")
        try:
            return json.loads(body)
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

    def exports(self) -> dict[str, Any]:
        request = Request(f"{self.base_url}{EXPORTS_PATH}", method="GET")
        return self._request(
            request,
            timeout=CAPABILITIES_TIMEOUT_SECONDS,
            failure=f"Could not ask {self.target.name} what it offers",
        )

    def pull(self, slug: str) -> bytes:
        request = Request(f"{self.base_url}{EXPORTS_PATH}{slug}/", method="GET")
        return self._fetch(
            request,
            timeout=EXPORT_TIMEOUT_SECONDS,
            failure=f"Pulling {slug} from {self.target.name} failed",
            accept="application/zip",
        )
