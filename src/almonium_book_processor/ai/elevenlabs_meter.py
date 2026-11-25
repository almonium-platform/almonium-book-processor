"""Read the owner's ElevenLabs subscription meter without spending any characters."""

from __future__ import annotations

import json
import re
import urllib.request
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from django.conf import settings

ACCOUNT = "api"
SUBSCRIPTION_URL = "https://api.elevenlabs.io/v1/user/subscription"
_ENV_LINE = re.compile(r"^ELEVENLABS_API_KEY=(.*)$")
_CURRENCY_SYMBOLS = {"usd": "$", "eur": "€", "gbp": "£"}


def _key_from_dotenv(path: Path) -> str:
    if not path.is_file():
        return ""
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        match = _ENV_LINE.match(line.strip())
        if not match:
            continue
        value = match.group(1).strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        if value:
            return value
    return ""


def elevenlabs_api_key() -> str:
    """The ElevenLabs API key, from settings or the sibling backend checkout's ``.env``."""

    direct = (getattr(settings, "ELEVENLABS_API_KEY", "") or "").strip()
    if direct:
        return direct
    backend_dir = (getattr(settings, "LEXICON_BACKEND_DIR", "") or "").strip()
    if not backend_dir:
        return ""
    return _key_from_dotenv(Path(backend_dir) / ".env")


def _format_plan_label(tier: str, invoice: dict[str, Any] | None, currency: str) -> str:
    label = tier.replace("_", " ").strip().title() if tier else ""
    cents = (invoice or {}).get("amount_due_cents")
    if isinstance(cents, int) and cents > 0:
        symbol = _CURRENCY_SYMBOLS.get((currency or "").lower(), "$")
        price = f"{symbol}{cents / 100:.2f}/mo"
        return f"{label} · {price}" if label else price
    return label


def elevenlabs_meter(
    *,
    api_key: str | None = None,
    opener: Callable[..., Any] = urllib.request.urlopen,
) -> dict[str, Any] | None:
    """The ElevenLabs monthly character meter, or ``None`` when unconfigured or unreachable."""

    key = (api_key if api_key is not None else elevenlabs_api_key()).strip()
    if not key:
        return None
    request = urllib.request.Request(
        SUBSCRIPTION_URL,
        headers={"xi-api-key": key, "Accept": "application/json"},
    )
    try:
        with opener(request, timeout=15) as response:
            data = json.loads(response.read().decode("utf-8"))
        count = int(data["character_count"])
        limit = int(data["character_limit"])
        used_percent = min(100, round(count * 100 / limit)) if limit > 0 else 100
        reset_unix = data.get("next_character_count_reset_unix")
        resets_at = datetime.fromtimestamp(int(reset_unix), UTC) if reset_unix else None
        tier = str(data.get("tier") or "").strip()
        invoice = data.get("next_invoice") if isinstance(data.get("next_invoice"), dict) else None
        currency = str(data.get("currency") or "")
        return {
            "used_percent": used_percent,
            "units_used": max(0, count),
            "units_limit": max(0, limit),
            "resets_at": resets_at,
            "plan_type": tier,
            "plan_label": _format_plan_label(tier, invoice, currency),
            "renews_on": resets_at.astimezone().date() if resets_at is not None else None,
        }
    except Exception:  # a meter that cannot be read must never fail the run it surrounds
        return None
