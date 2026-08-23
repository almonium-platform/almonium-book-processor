from __future__ import annotations

import json
import tempfile
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from django.conf import settings


class OpenAIBatchProvider:
    """Small provider boundary around the OpenAI Batch API."""

    name = "openai"

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
            return self.client.batches.create(
                input_file_id=input_file.id,
                endpoint="/v1/responses",
                completion_window="24h",
                metadata=metadata,
            )
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)

    def retrieve(self, batch_id: str) -> Any:
        return self.client.batches.retrieve(batch_id)

    def output_lines(self, output_file_id: str) -> list[dict[str, Any]]:
        content = self.client.files.content(output_file_id)
        text = content.text if hasattr(content, "text") else content.read().decode()
        return [json.loads(line) for line in text.splitlines() if line.strip()]
