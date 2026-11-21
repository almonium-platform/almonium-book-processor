"""A call made for work outside the processor: through the gateway, bought once, recorded."""

from __future__ import annotations

import io
import json
from decimal import Decimal

import pytest
from django.core.management import call_command

from almonium_book_processor.ai.cli_calls import AllowanceUsedUp, CallFailed
from almonium_book_processor.catalog import budgets, outside_calls
from almonium_book_processor.catalog.models import AIRun, ProviderBudget

pytestmark = pytest.mark.django_db

SCHEMA = {
    "type": "object",
    "required": ["rulings"],
    "additionalProperties": False,
    "properties": {"rulings": {"type": "array"}},
}
REQUEST = {
    "seat": "antigravity:gemini-4-carbon:medium",
    "purpose": "lexicon_review_rule",
    "caller": "review_v4",
    "input": "The entry and its findings.",
    "schema": SCHEMA,
}
USAGE = {
    "input_tokens": 10_000,
    "output_tokens": 2_000,
    "input_tokens_details": {"cached_tokens": 4_000},
    "output_tokens_details": {"reasoning_tokens": 1_500},
}


@pytest.fixture(autouse=True)
def plans(settings):
    settings.AI_PLANS = "codex,claude-code,antigravity"


class Fake:
    def __init__(self, *, error=None):
        self.bodies, self.error = [], error

    def respond(self, body):
        self.bodies.append(body)
        if self.error:
            raise self.error
        return {
            "id": "call-1",
            "status": "completed",
            "plan_account": "antigravity-cli",
            "output": [{"content": [{"type": "output_text", "text": '{"rulings": []}'}]}],
            "usage": USAGE,
        }


def test_a_request_is_asked_on_its_seat_and_recorded_in_the_ledger():
    fake = Fake()

    said = outside_calls.ask(REQUEST, provider=fake)

    assert said["status"] == "completed" and json.loads(said["text"]) == {"rulings": []}
    assert not said["cached"] and said["plan_account"] == "antigravity-cli"
    body = fake.bodies[0]
    assert body["model"] == "gemini-4-carbon" and body["reasoning"] == {"effort": "medium"}
    assert body["text"]["format"]["schema"] == SCHEMA and "tools" not in body
    run = AIRun.objects.get()
    assert run.status == AIRun.Status.SUCCEEDED and run.edition is None
    assert run.model_configuration.provider == "antigravity"
    assert run.model_configuration.purpose == "lexicon_review_rule"
    assert (run.input_tokens, run.cached_input_tokens, run.output_tokens) == (10_000, 4_000, 2_000)
    assert run.estimated_cost_usd > 0 and said["cost_usd"] == float(run.estimated_cost_usd)
    # the caller keeps its request; the ledger keeps the answer and what the request weighed
    assert "input" not in run.request_payload and run.request_payload["caller"] == "review_v4"
    # the plan's month counts it, so the owner's cap holds the dictionary as it holds a book
    assert budgets.spent("antigravity") == run.estimated_cost_usd


def test_the_same_request_is_bought_once_whatever_it_is_called():
    fake = Fake()
    outside_calls.ask(REQUEST, provider=fake)

    again = outside_calls.ask(
        {**REQUEST, "purpose": "another_label", "caller": "someone"}, provider=fake
    )

    assert (
        again["cached"] and again["cost_usd"] == 0 and json.loads(again["text"]) == {"rulings": []}
    )
    assert len(fake.bodies) == 1 and AIRun.objects.count() == 1


@pytest.mark.parametrize(
    "change",
    [
        {"input": "Another entry."},
        {"instructions": "Other rules."},
        {"seat": "antigravity:gemini-4-carbon:high"},
        {"schema": {**SCHEMA, "required": []}},
        {"salt": "second reading"},
    ],
)
def test_what_is_asked_and_of_whom_makes_a_new_request(change):
    fake = Fake()
    outside_calls.ask(REQUEST, provider=fake)

    outside_calls.ask({**REQUEST, **change}, provider=fake)

    assert len(fake.bodies) == 2


def test_a_refused_allowance_holds_and_buys_nothing():
    said = outside_calls.ask(REQUEST, provider=Fake(error=AllowanceUsedUp("the week is used up")))

    assert said["status"] == "held" and "week is used up" in said["reason"]
    assert not AIRun.objects.exists()


def test_the_owners_cap_holds_the_dictionary_before_the_plan_is_asked(monkeypatch):
    asked = []
    monkeypatch.setattr(
        "almonium_book_processor.ai.antigravity_provider.AntigravityProvider._ask",
        lambda self, body: asked.append(body),
    )
    outside_calls.ask(REQUEST, provider=Fake())
    ProviderBudget.objects.create(provider="antigravity", monthly_usd=Decimal("0.00"))

    said = outside_calls.ask({**REQUEST, "input": "Another entry."})

    assert said["status"] == "held" and "cap" in said["reason"]
    assert asked == [] and AIRun.objects.count() == 1


def test_a_call_that_failed_after_it_was_paid_is_recorded_failed_and_asked_again():
    broken = CallFailed("the answer is not JSON", {"usage": USAGE})

    said = outside_calls.ask(REQUEST, provider=Fake(error=broken))

    assert said == {"status": "failed", "error": "the answer is not JSON"}
    run = AIRun.objects.get()
    assert run.status == AIRun.Status.FAILED and run.estimated_cost_usd > 0
    fake = Fake()
    assert outside_calls.ask(REQUEST, provider=fake)["status"] == "completed"
    assert len(fake.bodies) == 1


def test_a_codex_reader_may_answer_in_prose_and_search_the_web():
    fake = Fake()

    outside_calls.ask(
        {
            "seat": "codex:gpt-6-astra:medium:search",
            "purpose": "lexicon_review_read",
            "input": "Ten entries.",
        },
        provider=fake,
    )

    body = fake.bodies[0]
    assert body["model"] == "gpt-6-astra" and body["text"]["format"] == {"type": "text"}
    assert body["tools"] == [{"type": "web_search"}]


@pytest.mark.parametrize(
    ("change", "why"),
    [
        ({"seat": "antigravity:gemini-4-carbon:medium:search"}, "Only a codex seat searches"),
        ({"schema": None}, "answers in a JSON schema"),
        ({"purpose": ""}, "names its purpose"),
        ({"seat": "nobody:model"}, "effort is"),
    ],
)
def test_a_request_that_cannot_be_asked_is_refused_unpaid(change, why):
    with pytest.raises(outside_calls.Refused, match=why):
        outside_calls.ask({**REQUEST, **change}, provider=Fake())
    assert not AIRun.objects.exists()


def test_the_command_reads_one_request_and_writes_one_answer(monkeypatch):
    monkeypatch.setattr(outside_calls, "ask", lambda request: {"status": "held", "reason": "cap"})
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(REQUEST)))
    out = io.StringIO()

    with pytest.raises(SystemExit) as stopped:
        call_command("ask", stdout=out)

    assert stopped.value.code == 75
    assert json.loads(out.getvalue().strip().splitlines()[-1]) == {
        "status": "held",
        "reason": "cap",
    }
