from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

from almonium_book_processor.catalog.models import Work
from almonium_book_processor.config.db_routers import LexiconRouter
from almonium_book_processor.config.settings import lexicon_database

SETTINGS_FILE = (
    Path(__file__).resolve().parents[1]
    / "src"
    / "almonium_book_processor"
    / "config"
    / "settings.py"
)


def load_settings(monkeypatch, **env: str):
    """Import settings.py afresh under the given environment, without touching Django's."""
    for name in ("LEXICON_DATABASE_URL", "DATABASE_URL"):
        monkeypatch.delenv(name, raising=False)
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    spec = importlib.util.spec_from_file_location("_settings_under_test", SETTINGS_FILE)
    module = importlib.util.module_from_spec(spec)
    sys.modules.pop("_settings_under_test", None)
    spec.loader.exec_module(module)
    return module


def test_settings_have_no_lexicon_alias_without_the_variable(monkeypatch):
    loaded = load_settings(monkeypatch)

    assert set(loaded.DATABASES) == {"default"}
    assert loaded.DATABASE_ROUTERS == ["almonium_book_processor.config.db_routers.LexiconRouter"]


def test_settings_add_a_read_only_lexicon_alias_from_the_variable(monkeypatch):
    loaded = load_settings(
        monkeypatch,
        LEXICON_DATABASE_URL="postgresql://reader:p%40ss@pgbouncer:6432/almonium_staging",
    )

    lexicon = loaded.DATABASES["lexicon"]
    assert lexicon["ENGINE"] == "django.db.backends.postgresql"
    assert lexicon["NAME"] == "almonium_staging"
    assert lexicon["USER"] == "reader"
    assert lexicon["PASSWORD"] == "p@ss"
    assert lexicon["HOST"] == "pgbouncer"
    assert lexicon["PORT"] == 6432
    assert lexicon["OPTIONS"]["options"] == "-c default_transaction_read_only=on"
    assert lexicon["CONN_MAX_AGE"] == 60
    assert loaded.DATABASES["default"]["ENGINE"] == "django.db.backends.sqlite3"


def test_the_read_only_option_is_postgres_only():
    assert "OPTIONS" not in lexicon_database("sqlite:///lexicon.sqlite3")


@pytest.fixture
def router():
    return LexiconRouter()


def test_the_router_refuses_to_migrate_into_the_lexicon(router):
    assert router.allow_migrate("lexicon", "catalog") is False
    assert router.allow_migrate("lexicon", "catalog", model_name="work") is False
    assert router.allow_migrate("lexicon", "auth") is False
    assert router.allow_migrate("lexicon", "contenttypes") is False


def test_the_router_leaves_the_default_database_to_django(router):
    assert router.allow_migrate("default", "catalog") is None
    assert router.db_for_read(Work) is None
    assert router.allow_relation(Work(), Work()) is None


def test_the_router_never_writes_to_the_lexicon(router):
    assert router.db_for_write(Work) is None
    assert router.db_for_write(Work, instance=Work()) != "lexicon"
