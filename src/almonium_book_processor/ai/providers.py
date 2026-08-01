from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True, slots=True)
class AIRequest:
    system_prompt: str
    user_prompt: str
    output_schema: dict[str, Any]
    parameters: dict[str, Any] = field(default_factory=dict)
    idempotency_key: str = ""


@dataclass(frozen=True, slots=True)
class AIResponse:
    provider_request_id: str
    output: dict[str, Any]
    input_tokens: int
    output_tokens: int
    raw_response: dict[str, Any]


class AIProvider(Protocol):
    """Boundary implemented by OpenAI or another provider once credentials are supplied."""

    def generate(self, *, model: str, request: AIRequest) -> AIResponse: ...
