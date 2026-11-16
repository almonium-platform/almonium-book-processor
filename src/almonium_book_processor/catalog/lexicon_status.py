"""The dictionary's state for the Operations page's Entries tab.

The entries are written on the owner's machine by the backend's lexicon scripts, not by this
processor, so nothing here is in the database: the backend's ``lexicon_status.py`` sums the
entry files into one JSON file every quarter of an hour, and this reads it
(``LEXICON_STATUS_FILE``). Where no file is configured or written, the tab says so.
"""

from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from almonium_book_processor.ai.seats import versioned

LANGUAGE_NAMES = {
    "en": "English",
    "de": "German",
    "fr": "French",
    "es": "Spanish",
    "it": "Italian",
    "pt": "Portuguese",
    "uk": "Ukrainian",
}
# A status older than this is shown as stale: the timer that writes it has stopped.
STALE = timedelta(hours=1)
# check_v4.py's names for its faults, as a reader of the page understands them
FAULT_NAMES = {
    "schema": "breaks the schema",
    "definition of N words": "definition too short or long",
    "example of N words": "example too short or long",
    "headword in definition": "headword in its definition",
    "formula": "dictionary formula",
}


def lexicon_status() -> dict | None:
    """The status as the page shows it, or None when there is none to read."""

    path = Path(settings.LEXICON_STATUS_FILE) if settings.LEXICON_STATUS_FILE else None
    if path is None or not path.is_file():
        return None
    try:
        raw = json.loads(path.read_text())
    except (OSError, ValueError):
        return None
    built = parse_datetime(raw.get("built_at") or "")
    languages = []
    for row in raw.get("languages", []):
        entries = row.get("entries") or 0
        faults = row.get("faults") or {}
        languages.append(
            {
                **row,
                "name": LANGUAGE_NAMES.get(row["lang"], row["lang"]),
                "by_writer": [
                    {"writer": writer_label(name), "count": count}
                    for name, count in (row.get("by_writer") or {}).items()
                ],
                "fault_share": _percent(row.get("with_faults") or 0, entries),
                "faults": [
                    {
                        "name": FAULT_NAMES.get(kind, kind),
                        "count": count,
                        "share": _percent(count, entries),
                    }
                    for kind, count in faults.items()
                ],
                "queue_done": _percent(
                    (row.get("queue") or 0) - (row.get("queue_left") or 0), row.get("queue") or 0
                ),
            }
        )
    writers = [
        {
            **w,
            "label": writer_label(w["writer"]),
            "first": parse_datetime(w.get("first") or ""),
            "last": parse_datetime(w.get("last") or ""),
        }
        for w in raw.get("writers", [])
    ]
    totals = {
        key: sum(row.get(key) or 0 for row in raw.get("languages", []))
        for key in ("entries", "rejected", "last_day", "queue_left", "to_mend", "failed")
    }
    return {
        "built_at": built,
        "stale": built is None or timezone.now() - built > STALE,
        "queue": raw.get("queue", ""),
        "languages": languages,
        "writers": writers,
        "totals": totals,
        # the headword lists a writer can be given, by their name without the language
        "list_names": sorted(
            {name for names in (raw.get("lists") or {}).values() for name in names}
        ),
    }


def writer_label(directory: str) -> str:
    """A writer directory named the way the page names models: cc-claude-opus-5-5-v4 is
    "Opus 5.5 · v4", mend-claude-opus-5-5-v4 "Opus 5.5 mending · v4"."""

    name, _, prompt = directory.rpartition("-v")
    name = name or directory
    mending = name.startswith("mend-")
    for prefix in ("mend-", "cc-", "codex-"):
        name = name.removeprefix(prefix)
    for effort in ("-high", "-medium", "-low"):
        name = name.removesuffix(effort)
    model = versioned(name).replace("claude-", "")
    label = model[:1].upper() + model[1:]
    return f"{label}{' mending' if mending else ''}" + (f" · v{prompt}" if prompt.isdigit() else "")


def _percent(part: int, whole: int) -> str:
    return f"{round(100 * part / whole)}%" if whole else "–"
