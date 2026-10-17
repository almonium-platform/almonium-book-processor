from __future__ import annotations

from django.conf import settings


class LexiconRouter:
    """Keeps the lexicon alias read-only from Django's side.

    The alias is another service's database (the backend's dictionary). Nothing of ours is
    migrated into it and no write is ever routed there; reads happen only where the code asks
    for the alias by name. The PostgreSQL role behind it refuses writes as well; this router
    is the first line, not the only one.
    """

    @property
    def alias(self) -> str:
        return settings.LEXICON_DATABASE_ALIAS

    def db_for_read(self, model, **hints):
        return None

    def db_for_write(self, model, **hints):
        # None means Django's default database; the lexicon alias is never chosen.
        return None

    def allow_relation(self, obj1, obj2, **hints):
        return None

    def allow_migrate(self, db, app_label, model_name=None, **hints):
        if db == self.alias:
            return False
        return None
