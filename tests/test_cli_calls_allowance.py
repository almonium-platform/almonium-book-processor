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


def test_claudes_session_limit_is_a_used_up_allowance_with_its_reset_time():
    """On 24 October 2026 this wording was taken for a broken call: tried twice, re-asked, and
    sixty productions burned their starts in fifteen minutes."""

    def call():
        raise RuntimeError(
            'Claude Code exited with 1: {"is_error":true,"result":"You\'ve hit your session '
            'limit · resets 6:10pm (UTC)"}'
        )

    with pytest.raises(AllowanceUsedUp) as refused:
        tried_twice(call, pause=lambda _: None)

    assert str(refused.value).startswith(ALLOWANCE_USED_UP)
    assert refused.value.until == "6:10pm (UTC)"


def test_a_network_that_stays_down_through_the_retry_is_an_outage_not_a_broken_call():
    """On the evening of 25 October 2026 the laptop lost its network and every book burned its
    starts on "can't reach the API server"; the pipeline now holds and waits for a provider."""

    from almonium_book_processor.ai.cli_calls import NETWORK_DOWN, NetworkDown

    calls = []

    def call():
        calls.append(1)
        raise RuntimeError(
            "Claude Code exited with 1: API Error: Can't reach the API server — check your "
            "internet or DNS (EAI_AGAIN)"
        )

    with pytest.raises(NetworkDown) as down:
        tried_twice(call, pause=lambda _: None)

    # tried once more after the pause, as a passing blip deserves; then named as an outage
    assert len(calls) == 2
    assert str(down.value).startswith(NETWORK_DOWN)


def test_a_passing_network_blip_is_retried_and_forgiven():
    answers = [RuntimeError("Codex returned no answer: workspace routing discovery failed"), None]

    def call():
        error = answers.pop(0)
        if error:
            raise error
        return {"usage": {"input_tokens": 5}}

    assert tried_twice(call, pause=lambda _: None)["usage"]["input_tokens"] == 5
