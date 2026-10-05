"""A call to a plan's CLI, tried once more when it fails for a passing reason.

A long step makes hundreds of these calls, and before this one timeout or one garbled answer
failed the whole step. The CLI's own failures are worth a second try: it exited with an error,
it timed out, or it answered with something that is not the JSON asked for. A plan whose
allowance is used up is not: the second call would fail the same way.
"""

from __future__ import annotations

import logging
import re
import subprocess
import time
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)

RETRY_PAUSE_SECONDS = 15.0
_ALLOWANCE_USED_UP = re.compile(r"usage limit|limit reached", re.IGNORECASE)


def tried_twice(
    call: Callable[[], dict[str, Any]], *, pause: Callable[[float], None] = time.sleep
) -> dict[str, Any]:
    """``call()``, and once more after a short pause if the CLI failed in passing."""

    try:
        return call()
    except (RuntimeError, subprocess.TimeoutExpired) as error:
        if _ALLOWANCE_USED_UP.search(str(error)):
            raise
        logger.warning("A plan CLI call failed and is tried once more: %s", str(error)[:300])
    pause(RETRY_PAUSE_SECONDS)
    return call()
