"""A model call made for work that lives outside this processor, through the same gateway.

The dictionary's review loop is the backend's ``scripts/lexicon_research/review_v4.py``. It
used to call the plans' command lines itself, so its calls passed no monthly cap, ignored an
account the owner had paused and left nothing in the ledger. It now hands each request to
``manage.py ask`` (one JSON object in, one out; the contract is in that command), and this
module answers it like any step here: a seat routed by ``ai/gateway``, the provider's cap
checked first, the call recorded as an ``AIRun``.

A request is bought once and found again by its content: the seat, the instructions, the
input, the shape of the answer, whether the web may be searched and, for a request that shows
the model pictures, what is in those files (never where they lie). The caller's ``salt`` is
for a caller that means to ask the same thing again (a measure of how answers vary). The
purpose and the caller's name are labels and move nothing. A refused allowance or cap buys
nothing and records nothing: the caller holds and asks again. A call that failed after it used
tokens is recorded failed with what it used, and is asked again when the caller asks.

The ledger keeps the answer (it is what the content buys) and not the request: the caller
keeps its own, and a writer's rules are fifteen thousand tokens sent with every word.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from django.utils import timezone

from almonium_book_processor.ai import gateway
from almonium_book_processor.ai.cli_calls import AllowanceUsedUp, NetworkDown, spent_by
from almonium_book_processor.ai.seats import Seat
from almonium_book_processor.catalog.models import AIRun, ModelConfiguration, PromptTemplate

VERSION = 1
PROMPT_NAME = "outside-call"
TEXT = {"type": "text"}
# a request may show the model a few pictures; only Claude Code can be handed a file to look at
MAX_IMAGES = 8
MAX_IMAGE_BYTES = 5_000_000


class Refused(ValueError):
    """The request cannot be asked as written; nothing was paid."""


def _seat_and_search(written: str) -> tuple[Seat, bool]:
    """A seat as the gateway writes it, with ``:search`` after it or not."""

    written = (written or "").strip()
    search = written.endswith(":search")
    return gateway.route(written.removesuffix(":search")), search


def identity(request: dict[str, Any]) -> str:
    seat, search = _seat_and_search(request["seat"])
    content = {
        "version": VERSION,
        "seat": [seat.provider, seat.model, seat.effort or "medium"],
        "search": search,
        "instructions": request.get("instructions") or "",
        "input": request["input"],
        "schema": request.get("schema"),
        "salt": request.get("salt") or "",
        # absent for a request without pictures, so every identity bought before stays found
        **({"images": _image_digests(request["images"])} if request.get("images") else {}),
    }
    return hashlib.sha256(
        json.dumps(content, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()


def _image_digests(images: list[str]) -> list[str]:
    return [hashlib.sha256(Path(image).read_bytes()).hexdigest() for image in images]


def _images(request: dict[str, Any], seat: Seat) -> list[str]:
    """The pictures a request shows the model, as absolute paths; ``Refused`` if it cannot."""

    images = request.get("images")
    if images is None:
        return []
    if not isinstance(images, list) or not all(isinstance(image, str) for image in images):
        raise Refused("A request's images are a list of file paths")
    if not images:
        return []
    if seat.provider != "claude-code":
        raise Refused("Only a claude-code seat is shown images here")
    if len(images) > MAX_IMAGES:
        raise Refused(f"A request shows at most {MAX_IMAGES} images")
    for image in images:
        path = Path(image)
        if not path.is_absolute() or not path.is_file():
            raise Refused(f"An image is an absolute path to a file: {image[:200]}")
        if path.stat().st_size > MAX_IMAGE_BYTES:
            raise Refused(f"An image is at most {MAX_IMAGE_BYTES} bytes: {image[:200]}")
    return images


def _body(request: dict[str, Any], seat: Seat, search: bool) -> dict[str, Any]:
    schema = request.get("schema")
    return {
        "model": seat.model,
        "instructions": request.get("instructions") or "",
        "input": request["input"],
        "reasoning": {"effort": seat.effort or "medium"},
        "store": False,
        "text": {
            "format": (
                {"type": "json_schema", "name": "answer", "strict": True, "schema": schema}
                if schema
                else TEXT
            )
        },
        **({"tools": [{"type": "web_search"}]} if search else {}),
        **({"images": request["images"]} if request.get("images") else {}),
    }


def _records(seat: Seat, purpose: str) -> tuple[ModelConfiguration, PromptTemplate]:
    configuration, _ = ModelConfiguration.objects.get_or_create(
        name=f"{purpose}-{seat.provider}-{seat.model}"[:120],
        defaults={"provider": seat.provider, "model": seat.model, "purpose": purpose},
    )
    prompt, _ = PromptTemplate.objects.get_or_create(
        name=PROMPT_NAME,
        version=VERSION,
        defaults={
            "purpose": "outside_call",
            "system_prompt": "The caller's own; each request carries its instructions.",
            "user_template": "{input}",
            "output_schema": {},
            "active": True,
        },
    )
    return configuration, prompt


def _usage(spent: dict[str, Any]) -> dict[str, int]:
    usage = spent.get("usage") or {}
    return {
        "input_tokens": usage.get("input_tokens") or 0,
        "cached_input_tokens": (usage.get("input_tokens_details") or {}).get("cached_tokens") or 0,
        "output_tokens": usage.get("output_tokens") or 0,
        "reasoning_tokens": (usage.get("output_tokens_details") or {}).get("reasoning_tokens") or 0,
    }


def _record(request, seat, digest, spent, *, text="", error="", started) -> AIRun:
    purpose = str(request["purpose"])[:50]
    configuration, prompt = _records(seat, purpose)
    usage = _usage(spent)
    run = AIRun(
        model_configuration=configuration,
        prompt_template=prompt,
        input_hash=digest,
        status=AIRun.Status.FAILED if error else AIRun.Status.SUCCEEDED,
        provider_request_id=str(spent.get("id") or "")[:255],
        request_payload={
            "caller": str(request.get("caller") or "")[:120],
            "seat": request["seat"],
            "bytes": len(request["input"].encode("utf-8")),
        },
        response_payload={"text": text} if text else {},
        error=error[:2000],
        started_at=started,
        finished_at=timezone.now(),
    )
    run.add_attempt_usage(
        **usage,
        estimated_cost_usd=gateway.cost(
            seat,
            input_tokens=usage["input_tokens"],
            cached_input_tokens=usage["cached_input_tokens"],
            output_tokens=usage["output_tokens"],
            response=spent,
        ),
        plan_account=spent.get("plan_account", ""),
    )
    run.save()
    return run


def _said(run: AIRun, *, cached: bool) -> dict[str, Any]:
    return {
        "status": "completed",
        "text": run.response_payload["text"],
        "cached": cached,
        "provider": run.model_configuration.provider,
        "model": run.model_configuration.model,
        "plan_account": run.plan_account,
        "usage": {
            "input_tokens": run.input_tokens,
            "cached_input_tokens": run.cached_input_tokens,
            "output_tokens": run.output_tokens,
            "reasoning_tokens": run.reasoning_tokens,
        },
        # nothing is paid for an answer found again
        "cost_usd": 0.0 if cached else float(run.estimated_cost_usd or 0),
    }


def ask(request: dict[str, Any], *, provider=None) -> dict[str, Any]:
    """The answer to one request from outside: found by its content, else bought and recorded.

    ``{"status": "completed", "text": …}``, ``{"status": "held", "reason": …}`` when a cap, a
    pause or a plan's wall refused (nothing paid, ask again later), or ``{"status": "failed",
    "error": …}``. ``Refused`` when the request itself is wrong.
    """

    for name in ("seat", "purpose", "input"):
        if not isinstance(request.get(name), str) or not request[name].strip():
            raise Refused(f"A request names its {name}")
    try:
        seat, search = _seat_and_search(request["seat"])
    except ValueError as error:
        raise Refused(str(error)) from error
    if search and seat.provider != "codex":
        raise Refused("Only a codex seat searches the web here")
    if not request.get("schema") and seat.provider != "codex":
        raise Refused(f"A {seat.provider} seat answers in a JSON schema; the request has none")
    if reason := gateway.unavailable(seat):
        raise Refused(reason)
    _images(request, seat)

    digest = identity(request)
    found = (
        AIRun.objects.filter(
            input_hash=digest,
            status=AIRun.Status.SUCCEEDED,
            prompt_template__name=PROMPT_NAME,
        )
        .select_related("model_configuration")
        .first()
    )
    if found is not None and found.response_payload.get("text"):
        return _said(found, cached=True)

    started = timezone.now()
    try:
        response = (provider or gateway.provider(seat)).respond(_body(request, seat, search))
    except (AllowanceUsedUp, NetworkDown) as held:
        return {"status": "held", "reason": str(held)[:500]}
    except Exception as error:
        spent = spent_by(error) or {}
        if spent:
            # paid for though it cannot be used: the ledger says so, and the next ask buys again
            _record(request, seat, digest, spent, error=str(error), started=started)
        return {"status": "failed", "error": str(error)[:500]}
    text = response["output"][0]["content"][0]["text"]
    return _said(_record(request, seat, digest, response, text=text, started=started), cached=False)
