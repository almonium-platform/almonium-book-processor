import pytest


@pytest.fixture(autouse=True)
def no_resting_plan_accounts():
    """A plan account that refused in one test must not rest into the next."""

    from almonium_book_processor.ai import cli_calls

    cli_calls._resting_until.clear()
    yield
    cli_calls._resting_until.clear()
