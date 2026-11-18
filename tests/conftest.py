import pytest


@pytest.fixture(autouse=True)
def no_resting_plan_accounts():
    """A plan account that refused in one test must not rest into the next."""

    from almonium_book_processor.ai import cli_calls

    cli_calls._resting_until.clear()
    yield
    cli_calls._resting_until.clear()


@pytest.fixture(autouse=True)
def no_remembered_vectors():
    """Fake embeddings from one test must not answer for the same text in the next."""

    from almonium_book_processor.processing import sentence_correspondence

    sentence_correspondence._vectors.clear()
    yield
    sentence_correspondence._vectors.clear()


@pytest.fixture(autouse=True)
def no_budget_check_without_a_database(request, monkeypatch):
    """A provider's unit test has no database to read caps from; a database test checks them."""

    if request.node.get_closest_marker("django_db") or {"db", "transactional_db"} & set(
        request.fixturenames
    ):
        return
    from almonium_book_processor.catalog import budgets

    monkeypatch.setattr(budgets, "check", lambda *args, **kwargs: None)
