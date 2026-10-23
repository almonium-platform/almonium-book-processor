import pytest

from almonium_book_processor.catalog.production import STARTS, Held, _log, _started


def test_a_hold_after_repeated_starts_names_the_error_that_stopped_the_step():
    # Dom Casmurro and O Cortiço held as "'probe B2' was started 2 times and did not finish" while
    # the log held the reason: no chapter fit the pilot limits.
    state = {"starts": {"probe B2": STARTS}, "log": []}
    _log(state, "info", "source", "The source's chapters have their levels.")
    _log(
        state,
        "warn",
        "probe",
        "ValueError: No chapter fits the pilot limits; split long chapters first.; trying again",
    )
    with pytest.raises(Held) as held:
        _started(state, "probe B2")
    assert "did not finish. Last: ValueError: No chapter fits the pilot limits" in str(held.value)
    assert str(held.value).endswith("split long chapters first.")


def test_a_hold_without_a_logged_error_keeps_the_plain_message():
    state = {"starts": {"book B1": STARTS}, "log": []}
    with pytest.raises(Held, match=r"'book B1' was started \d+ times and did not finish\.$"):
        _started(state, "book B1")
