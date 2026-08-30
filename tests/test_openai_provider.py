from __future__ import annotations

from types import SimpleNamespace

import pytest

from almonium_book_processor.ai.openai_provider import OpenAIBatchProvider


class FakeFiles:
    def __init__(self, statuses: list[str]) -> None:
        self.statuses = statuses
        self.retrieve_calls = 0

    def create(self, *, file, purpose):  # noqa: A002
        return SimpleNamespace(id="file-test", purpose=purpose)

    def retrieve(self, file_id):
        index = min(self.retrieve_calls, len(self.statuses) - 1)
        self.retrieve_calls += 1
        return SimpleNamespace(
            id=file_id, status=self.statuses[index], status_details="unusable jsonl"
        )


class FakeBatches:
    def __init__(self, failures: int = 0) -> None:
        self.failures = failures
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if len(self.calls) <= self.failures:
            raise RuntimeError(
                f"Cannot find file {kwargs['input_file_id']}, or organization "
                "org-test does not have access to it."
            )
        return SimpleNamespace(
            id="batch-test", status="validating", input_file_id=kwargs["input_file_id"]
        )


def build_provider(statuses: list[str], *, batch_failures: int = 0) -> OpenAIBatchProvider:
    provider = OpenAIBatchProvider.__new__(OpenAIBatchProvider)
    provider.client = SimpleNamespace(
        files=FakeFiles(statuses), batches=FakeBatches(batch_failures)
    )
    provider.file_ready_poll_seconds = 0
    provider.batch_create_backoff_seconds = 0
    return provider


REQUESTS = [{"custom_id": "chapter-1", "method": "POST", "url": "/v1/responses", "body": {}}]


def test_batch_waits_for_the_upload_to_be_processed() -> None:
    provider = build_provider(["pending", "pending", "processed"])

    batch = provider.submit(REQUESTS, metadata={"purpose": "translation"})

    assert batch.id == "batch-test"
    # The batch must not be created until the upload reports processed.
    assert provider.client.files.retrieve_calls == 3
    assert provider.client.batches.calls[0]["input_file_id"] == "file-test"


def test_upload_error_status_is_reported_not_submitted() -> None:
    provider = build_provider(["error"])

    with pytest.raises(RuntimeError, match="unusable jsonl"):
        provider.submit(REQUESTS, metadata={})

    assert provider.client.batches.calls == []


def test_upload_that_never_processes_times_out() -> None:
    provider = build_provider(["pending"])
    provider.file_ready_timeout_seconds = 0

    with pytest.raises(RuntimeError, match="still pending"):
        provider.submit(REQUESTS, metadata={})

    assert provider.client.batches.calls == []


def test_batch_creation_retries_a_transiently_missing_file() -> None:
    provider = build_provider(["processed"], batch_failures=2)

    batch = provider.submit(REQUESTS, metadata={})

    assert batch.id == "batch-test"
    assert len(provider.client.batches.calls) == 3


def test_batch_creation_does_not_retry_unrelated_errors() -> None:
    provider = build_provider(["processed"])

    def explode(**kwargs):
        provider.client.batches.calls.append(kwargs)
        raise RuntimeError("model not found")

    provider.client.batches.create = explode

    with pytest.raises(RuntimeError, match="model not found"):
        provider.submit(REQUESTS, metadata={})

    assert len(provider.client.batches.calls) == 1
