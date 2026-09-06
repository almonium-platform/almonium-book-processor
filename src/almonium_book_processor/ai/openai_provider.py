from __future__ import annotations

import json
import tempfile
import time
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from django.conf import settings


class OpenAIBatchProvider:
    """Small provider boundary around the OpenAI Batch API."""

    name = "openai"

    # A freshly uploaded file is not immediately usable by the Batch service.
    # Creating the batch too early is rejected with "Cannot find file ...", so
    # wait for the upload to report `processed` and still retry once or twice
    # in case the two services are briefly inconsistent.
    file_ready_timeout_seconds = 300.0
    file_ready_poll_seconds = 2.0
    batch_create_attempts = 3
    batch_create_backoff_seconds = 5.0

    def __init__(self) -> None:
        if not settings.OPENAI_API_KEY:
            raise RuntimeError("OPENAI_API_KEY is not configured")
        try:
            from openai import OpenAI
        except ImportError as error:
            raise RuntimeError("Install worker dependencies to use OpenAI alignment") from error
        self.client = OpenAI(api_key=settings.OPENAI_API_KEY)

    def submit(self, requests: Iterable[dict[str, Any]], *, metadata: dict[str, str]) -> Any:
        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as stream:
                temporary_path = Path(stream.name)
                for request in requests:
                    stream.write(json.dumps(request, ensure_ascii=False) + "\n")
            with temporary_path.open("rb") as stream:
                input_file = self.client.files.create(file=stream, purpose="batch")
            self._await_processed_file(input_file.id)
            return self._create_batch(input_file.id, metadata)
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)

    def _await_processed_file(self, file_id: str) -> None:
        deadline = time.monotonic() + self.file_ready_timeout_seconds
        while True:
            uploaded = self.client.files.retrieve(file_id)
            status = getattr(uploaded, "status", "processed")
            if status == "processed":
                return
            if status == "error":
                details = getattr(uploaded, "status_details", "") or "no detail provided"
                raise RuntimeError(f"OpenAI rejected batch input file {file_id}: {details}")
            if time.monotonic() >= deadline:
                raise RuntimeError(
                    f"OpenAI batch input file {file_id} was still {status} after "
                    f"{self.file_ready_timeout_seconds:.0f}s"
                )
            time.sleep(self.file_ready_poll_seconds)

    @staticmethod
    def _is_missing_input_file(error: Exception) -> bool:
        return "cannot find file" in str(error).lower()

    def _create_batch(self, file_id: str, metadata: dict[str, str]) -> Any:
        last_error: Exception | None = None
        for attempt in range(self.batch_create_attempts):
            try:
                return self.client.batches.create(
                    input_file_id=file_id,
                    endpoint="/v1/responses",
                    completion_window="24h",
                    metadata=metadata,
                )
            except Exception as error:
                if not self._is_missing_input_file(error):
                    raise
                last_error = error
                if attempt + 1 < self.batch_create_attempts:
                    time.sleep(self.batch_create_backoff_seconds * (attempt + 1))
        assert last_error is not None
        raise last_error

    def respond(self, body: dict[str, Any]) -> dict[str, Any]:
        """Run one Batch-shaped request body synchronously.

        Same body, same structured-output contract, no Batch service and no
        24-hour window. Used when Batch is unavailable or a fast result matters;
        it forfeits the 50% Batch discount.
        """

        response = self.client.responses.create(**body)
        return response.model_dump()

    def retrieve(self, batch_id: str) -> Any:
        return self.client.batches.retrieve(batch_id)

    def output_lines(self, output_file_id: str) -> list[dict[str, Any]]:
        content = self.client.files.content(output_file_id)
        text = content.text if hasattr(content, "text") else content.read().decode()
        return [json.loads(line) for line in text.splitlines() if line.strip()]


def response_output_text(body: dict[str, Any]) -> str:
    """Return the text of the first message in a Responses API body."""

    for item in body.get("output", []):
        if item.get("type") != "message":
            continue
        for content in item.get("content", []):
            if content.get("type") == "output_text":
                return content["text"]
    raise ValueError("OpenAI response contained no output text")
