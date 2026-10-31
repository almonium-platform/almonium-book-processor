import pytest


@pytest.fixture(autouse=True)
def no_resting_claude_accounts():
    """A Claude account that refused in one test must not rest into the next."""

    from almonium_book_processor.ai import claude_code_provider

    claude_code_provider._resting_until.clear()
    yield
    claude_code_provider._resting_until.clear()
