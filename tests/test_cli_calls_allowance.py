import pytest

from almonium_book_processor.ai.cli_calls import (
    ALLOWANCE_USED_UP,
    AllowanceUsedUp,
    CallFailed,
    tried_twice,
)

REFUSAL = (
    "Codex returned no answer: You’ve hit your usage limit. Visit "
    "https://chatgpt.com/settings/usage to purchase more credits or try again at "
    "Oct 30th, 2026 7:43 PM."
)


def test_a_used_up_allowance_is_not_tried_again_and_says_so_first():
    calls = []

    def call():
        calls.append(1)
        raise CallFailed(REFUSAL, {"usage": {"input_tokens": 0}})

    with pytest.raises(AllowanceUsedUp) as refused:
        tried_twice(call, pause=lambda _: None)

    assert len(calls) == 1
    assert str(refused.value).startswith(f"{ALLOWANCE_USED_UP}: Codex returned no answer")
    assert refused.value.until == "Oct 30th, 2026 7:43 PM"


def test_a_refusal_on_the_second_try_carries_what_the_first_try_used():
    answers = [
        CallFailed("Codex returned an answer that is not JSON", {"usage": {"input_tokens": 700}}),
        RuntimeError("Claude Code exited with 1: limit reached"),
    ]

    def call():
        raise answers.pop(0)

    with pytest.raises(AllowanceUsedUp) as refused:
        tried_twice(call, pause=lambda _: None)

    assert refused.value.spent["usage"]["input_tokens"] == 700
    assert refused.value.until is None


def test_a_passing_failure_is_still_tried_twice():
    answers = [RuntimeError("Claude Code exited with 1: boom"), {"ok": True}]

    def call():
        answer = answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer

    assert tried_twice(call, pause=lambda _: None) == {"ok": True}
