"""The dictionary's entry writers, started and paused from the Operations page.

An entry writer is the backend's ``scripts/lexicon_research/claude_code_writer.py`` on one Claude
account, for one language, from one headword list (``LexiconWriter``). The page only records what
the owner wants; the web container cannot start anything on the host. A timer on the host runs
``manage.py lexicon_writers --reconcile`` every five minutes, and ``reconcile`` makes the host
match the page: each writer that is on runs as the systemd user service
``almonium-lexicon-writer@<id>`` (under ``systemd-inhibit``, so the laptop does not sleep under
it), each one that is off is stopped, and every writer's state and last log line are written back
for the page. A writer that reaches the end of its list stops by itself and is switched off.

Two writers never share a language's list: they would write the same words. Entries are written
for the target languages only; Ukrainian is the bridge language glosses are written in.
"""

from __future__ import annotations

import os
import subprocess
from collections.abc import Callable
from pathlib import Path

from django.conf import settings
from django.utils import timezone

from almonium_book_processor.catalog.models import LexiconWriter

LANGUAGES = ("en", "de", "fr", "es", "it", "pt")
MODELS = ("claude-opus-5-5", "claude-fable-5-2")
EFFORTS = ("low", "medium", "high")
MAX_WORKERS = 6
SERVICE = "almonium-lexicon-writer"
UNIT = f"{SERVICE}@.service"


def claude_accounts() -> list[str]:
    """The Claude accounts a writer may use, by the name the meters give them (``.claude-2``).

    The meters' accounts, since the web container is not told the host's ``CLAUDE_CONFIG_DIRS``.
    """

    from almonium_book_processor.catalog.models import PlanAccount

    known = PlanAccount.objects.filter(provider="claude-code").order_by("account")
    named = [Path(path).expanduser().name for path in settings.CLAUDE_CONFIG_DIRS]
    return sorted(set(known.values_list("account", flat=True)) | set(named)) or [".claude"]


def add_writer(
    *,
    account: str,
    language: str,
    word_list: str,
    workers: int,
    pause_at_percent: int,
    model: str,
    effort: str,
    by: str,
) -> LexiconWriter:
    """A new writer, off until it is started; ValueError when the page asked for something wrong."""

    if account not in claude_accounts():
        raise ValueError(f"Choose one of the Claude accounts: {', '.join(claude_accounts())}.")
    if language not in LANGUAGES:
        raise ValueError(
            f"Entries are written for {', '.join(LANGUAGES)} only; "
            "Ukrainian is the bridge language."
        )
    word_list = word_list.strip()
    if not word_list or not all(c.isalnum() or c in "-_" for c in word_list):
        raise ValueError("Name the headword list as its file is named, e.g. v4-new or en-deep.")
    if not 1 <= workers <= MAX_WORKERS:
        raise ValueError(f"A writer has 1 to {MAX_WORKERS} workers.")
    if not 1 <= pause_at_percent <= 100:
        raise ValueError("Pause the writer at 1 to 100 percent of the five-hour window.")
    if model not in MODELS or effort not in EFFORTS:
        raise ValueError("Choose a model and an effort from the lists.")
    if LexiconWriter.objects.filter(language=language, word_list=word_list).exists():
        raise ValueError(
            f"A writer for the {language} list {word_list} exists already: "
            "two would write the same words."
        )
    return LexiconWriter.objects.create(
        account=account,
        language=language,
        word_list=word_list,
        workers=workers,
        pause_at_percent=pause_at_percent,
        model=model,
        effort=effort,
        changed_by=by[:150],
    )


def set_running(writer: LexiconWriter, running: bool, *, by: str) -> None:
    writer.running = running
    writer.changed_by = by[:150]
    writer.save(update_fields=["running", "changed_by", "updated_at"])


# ---------------------------------------------------------------------------------- on the host

Runner = Callable[..., subprocess.CompletedProcess]


def backend_dir() -> Path:
    return Path(settings.LEXICON_BACKEND_DIR).expanduser().resolve()


def log_path(writer_id: int) -> Path:
    return (
        backend_dir() / "scripts" / "lexicon_research" / "out" / "logs" / f"writer-{writer_id}.log"
    )


def unit_text() -> str:
    """The writers' systemd template, for this backend checkout and this shell's PATH."""

    backend = backend_dir()
    config = Path.home() / ".config" / "almonium"
    command = " ".join(
        [
            "/usr/bin/systemd-inhibit --what=sleep:idle",
            f'--who={SERVICE}-%i --why="dictionary entries" --mode=block',
            f"{backend}/scripts/.venv/bin/python scripts/lexicon_research/claude_code_writer.py",
            "--model ${MODEL} --effort ${EFFORT} --langs ${LANGUAGE} --headwords ${WORD_LIST}",
            "--workers ${WORKERS} --pause-session ${PAUSE_AT}",
        ]
    )
    return f"""[Unit]
Description=Almonium dictionary: entry writer %i, set on the book processor's Operations page

[Service]
WorkingDirectory={backend}
Environment=PATH={os.environ.get("PATH", "/usr/bin:/bin")}
EnvironmentFile={config}/lexicon-writer-%i.env
ExecStart={command}
StandardOutput=append:{backend}/scripts/lexicon_research/out/logs/writer-%i.log
StandardError=inherit
# a writer waits out plan limits itself; it ends only at the end of its list or on a crash
Restart=on-failure
RestartSec=60
# a stop cuts the words in flight; they are written again on the next start
TimeoutStopSec=20
"""


def env_text(writer: LexiconWriter) -> str:
    home = Path.home()
    return "\n".join(
        [
            f"CLAUDE_CONFIG_DIR={home / writer.account}",
            f"MODEL={writer.model}",
            f"EFFORT={writer.effort}",
            f"LANGUAGE={writer.language}",
            f"WORD_LIST={writer.word_list}",
            f"WORKERS={writer.workers}",
            f"PAUSE_AT={writer.pause_at_percent}",
            "",
        ]
    )


def _systemctl(runner: Runner, *args: str) -> subprocess.CompletedProcess:
    return runner(["systemctl", "--user", *args], capture_output=True, text=True, check=False)


def _state(runner: Runner, unit: str) -> str:
    """The service's state as systemd says it: active, activating, failed, inactive."""

    return _systemctl(runner, "is-active", unit).stdout.strip() or "inactive"


def _last_line(writer_id: int) -> str:
    path = log_path(writer_id)
    if not path.is_file():
        return ""
    with path.open("rb") as stream:
        stream.seek(max(0, path.stat().st_size - 4000))
        lines = [
            line for line in stream.read().decode("utf-8", "replace").splitlines() if line.strip()
        ]
    return lines[-1][:300] if lines else ""


def reconcile(*, runner: Runner = subprocess.run) -> list[str]:
    """Make the host's writer services match the page; what was done, one line each."""

    done = []
    systemd_dir = Path.home() / ".config" / "systemd" / "user"
    config = Path.home() / ".config" / "almonium"
    systemd_dir.mkdir(parents=True, exist_ok=True)
    config.mkdir(parents=True, exist_ok=True)
    unit_file = systemd_dir / UNIT
    if not unit_file.is_file() or unit_file.read_text() != unit_text():
        unit_file.write_text(unit_text())
        _systemctl(runner, "daemon-reload")
        done.append(f"wrote {UNIT}")
    log_path(0).parent.mkdir(parents=True, exist_ok=True)
    known = set()
    for writer in LexiconWriter.objects.all():
        unit = f"{SERVICE}@{writer.id}.service"
        known.add(unit)
        env_file = config / f"lexicon-writer-{writer.id}.env"
        changed = not env_file.is_file() or env_file.read_text() != env_text(writer)
        if changed:
            env_file.write_text(env_text(writer))
        state = _state(runner, unit)
        last = _last_line(writer.id)
        if writer.running:
            if state == "inactive" and last == "done":
                # the list is written: nothing to start again
                writer.running = False
                state = "finished"
                done.append(f"{unit}: finished its list")
            elif state not in ("active", "activating") or changed:
                _systemctl(runner, "restart" if changed and state == "active" else "start", unit)
                state = _state(runner, unit)
                done.append(f"{unit}: started ({state})")
        elif state in ("active", "activating"):
            _systemctl(runner, "stop", unit)
            state = _state(runner, unit)
            done.append(f"{unit}: stopped")
        writer.state = state[:40]
        writer.last_line = last
        writer.checked_at = timezone.now()
        writer.save(update_fields=["running", "state", "last_line", "checked_at", "updated_at"])
    # a writer removed on the page is stopped and forgotten
    listed = _systemctl(runner, "list-units", "--all", "--plain", "--no-legend", f"{SERVICE}@*")
    for line in listed.stdout.splitlines():
        unit = line.split()[0] if line.split() else ""
        if unit.startswith(f"{SERVICE}@") and unit not in known:
            _systemctl(runner, "stop", unit)
            done.append(f"{unit}: stopped, its writer was removed")
    return done
