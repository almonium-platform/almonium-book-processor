"""In-memory migrations for normalized artifacts produced by older processors."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from almonium_book_processor.models import SCHEMA_VERSION


def migrate_artifact_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Return a current-schema copy of a normalized artifact payload."""

    migrated = deepcopy(payload)
    version = migrated.get("schema_version")

    if version == 1:
        edition = migrated.get("edition", {})
        _rename(edition, "edition_id", "edition_slug")
        _rename(edition, "work_id", "work_slug")
        _rename(edition, "source_edition_id", "source_edition_slug")
        for block in migrated.get("blocks", []):
            _rename(block, "edition_id", "edition_slug")
            block["schema_version"] = 2
        migrated["schema_version"] = 2
        version = 2

    if version == 2:
        edition = migrated.get("edition", {})
        _rename(edition, "cefr_target", "cefr_level")
        for block in migrated.get("blocks", []):
            block["schema_version"] = SCHEMA_VERSION
        migrated["schema_version"] = SCHEMA_VERSION

    return migrated


def _rename(container: dict[str, Any], old_name: str, new_name: str) -> None:
    if old_name in container:
        container[new_name] = container.pop(old_name)
