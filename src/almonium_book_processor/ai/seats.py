"""A seat names who does a step: the provider, the model and, when it matters, the effort.

Written as ``provider:model`` or ``provider:model:effort``. The provider is ``openai`` for the
metered API, or ``codex`` or ``claude-code`` for a CLI signed in to one of the owner's plans.
A plan seat works only on the machine where that CLI is signed in, so deployed settings name
API seats and the owner's machine names plan seats for the same steps.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from almonium_book_processor.ai.pricing import has_price

PROVIDERS = ("openai", "codex", "claude-code")
PLAN_PROVIDERS = ("codex", "claude-code")
EFFORTS = ("low", "medium", "high")

# The Claude Code CLI is asked for a family and runs that family's current model. Records keep
# the name the CLI was given; pages print the model it stood for, read from the CLI's own
# ``modelUsage`` on 2026-10-05. Move a family here when the CLI moves it.
CLAUDE_CODE_MODELS = {"opus": "opus-5.5", "fable": "fable-5.1", "sonnet": "sonnet-5.5"}
_FAMILY = re.compile(rf"\b({'|'.join(CLAUDE_CODE_MODELS)})\b(?![-.]?\d)")


def versioned(names: str) -> str:
    """Model names as pages print them, each with its version, as the GPT names carry theirs."""

    return _FAMILY.sub(lambda match: CLAUDE_CODE_MODELS[match.group(1)], names)


@dataclass(frozen=True)
class Seat:
    provider: str
    model: str
    effort: str = ""

    @property
    def on_plan(self) -> bool:
        return self.provider in PLAN_PROVIDERS


def parse_seat(setting: str) -> Seat:
    provider, _, rest = setting.strip().partition(":")
    model, _, effort = rest.partition(":")
    if provider not in PROVIDERS or not model:
        raise ValueError(f"A seat is <{'|'.join(PROVIDERS)}>:<model>[:<effort>], not {setting!r}")
    if effort and effort not in EFFORTS:
        raise ValueError(f"A seat's effort is {', '.join(EFFORTS)}, not {effort!r}")
    if provider in PLAN_PROVIDERS and not has_price(model):
        # refused before any call is made, not after one used up part of the plan
        raise ValueError(f"No price is known for {model}; add it to ai/pricing.py")
    return Seat(provider, model, effort)


def provider_for(provider: str, model: str):
    """The provider object that makes a seat's calls."""

    # imported here: the CLI providers read settings when they are built
    from almonium_book_processor.ai.claude_code_provider import ClaudeCodeProvider
    from almonium_book_processor.ai.codex_provider import CodexProvider
    from almonium_book_processor.ai.openai_provider import OpenAIBatchProvider

    if provider == "claude-code":
        return ClaudeCodeProvider(model=model)
    if provider == "codex":
        return CodexProvider()
    return OpenAIBatchProvider()
