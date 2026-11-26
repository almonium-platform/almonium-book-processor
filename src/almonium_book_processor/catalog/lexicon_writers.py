"""The dictionary's entry writers, started and paused from the Operations page.

An entry writer is the backend's ``scripts/lexicon_research/claude_code_writer.py`` on one Claude
account, for one language, from one headword list (``LexiconWriter``). The page only records what
the owner wants; the web container cannot start anything on the host. A timer on the host runs
``manage.py lexicon_writers --reconcile`` every minute, and ``reconcile`` makes the host
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

from almonium_book_processor.catalog.models import LexiconPublishRun, LexiconWriter

LANGUAGES = ("en", "de", "fr", "es", "it", "pt")
VOICED_LANGUAGES = ("en", "de", "fr", "es")
PUBLISH_TARGETS = tuple(LexiconPublishRun.Target.values)
DEFAULT_LOCAL_BACKEND_URL = "http://localhost:9998/v1"
MODELS = ("claude-opus-5-5", "claude-fable-5-2")
# Google's plan has one login a machine (ai/antigravity_provider.ACCOUNT) and serves, beside
# its own models, Claude Opus on a meter apart. Its writer is the backend's seat_writer.py.
GEMINI_ACCOUNT = "antigravity-cli"
GEMINI_MODELS = ("gemini-4-carbon", "claude-opus-5-5")
EFFORTS = ("low", "medium", "high")
MAX_WORKERS = 6
SERVICE = "almonium-lexicon-writer"
UNIT = f"{SERVICE}@.service"


def claude_accounts() -> list[str]:
    """The Claude accounts a writer may use, by the name the meters give them (``.claude-2``).

    The meters' accounts, since the web container is not told the host's ``CLAUDE_CONFIG_DIRS``.
    """

    from almonium_book_processor.catalog.models import PlanAccount

    archived = set(
        PlanAccount.objects.filter(provider="claude-code", archived=True).values_list(
            "account", flat=True
        )
    )
    known = PlanAccount.objects.filter(provider="claude-code", archived=False).order_by("account")
    named = [
        Path(path).expanduser().name
        for path in settings.CLAUDE_CONFIG_DIRS
        if Path(path).expanduser().name not in archived
    ]
    return sorted((set(known.values_list("account", flat=True)) | set(named)) - archived) or [
        ".claude"
    ]


def provider_of(account: str) -> str:
    """The plan an account's writer runs on, as the meters name it."""

    return "antigravity" if account == GEMINI_ACCOUNT else "claude-code"


def accounts() -> list[str]:
    """Every account a writer may use: the Claude accounts, then Google's plan."""

    return [*claude_accounts(), GEMINI_ACCOUNT]


def choices() -> dict:
    """What the form that adds a writer offers."""

    return {
        "languages": LANGUAGES,
        "accounts": accounts(),
        "models": (*MODELS, *(m for m in GEMINI_MODELS if m not in MODELS)),
        "efforts": EFFORTS,
        "max_workers": MAX_WORKERS,
    }


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

    if account not in accounts():
        raise ValueError(f"Choose one of the accounts: {', '.join(accounts())}.")
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
    served = GEMINI_MODELS if account == GEMINI_ACCOUNT else MODELS
    if model not in served or effort not in EFFORTS:
        raise ValueError(
            f"Choose an effort from the list and a model {account} serves: {', '.join(served)}."
        )
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


def request_publish(*, target: str, languages: str = "", by: str = "") -> LexiconPublishRun:
    """Queue an ingest + publish pass to ``target`` for the host timer to pick up."""

    if target not in PUBLISH_TARGETS:
        raise ValueError(f"Choose one of: {', '.join(PUBLISH_TARGETS)}.")
    cleaned_langs = [lang.strip() for lang in languages.split(",") if lang.strip()]
    bad = [lang for lang in cleaned_langs if lang not in LANGUAGES]
    if bad:
        raise ValueError(f"Unknown language(s): {', '.join(bad)}.")
    if LexiconPublishRun.objects.filter(
        target=target,
        status__in=[LexiconPublishRun.Status.QUEUED, LexiconPublishRun.Status.RUNNING],
    ).exists():
        raise ValueError(f"A publish run to {target} is already queued or running.")
    return LexiconPublishRun.objects.create(
        target=target,
        languages=",".join(cleaned_langs),
        requested_by=by[:150],
    )


def publish_summary() -> dict:
    """Latest publish run per target, plus whether staging succeeded more recently than prod."""

    latest = {}
    for target in PUBLISH_TARGETS:
        latest[target] = LexiconPublishRun.objects.filter(target=target).first()
    staging = latest.get("staging")
    prod = latest.get("prod")
    staging_ok = bool(staging and staging.status == LexiconPublishRun.Status.SUCCEEDED)
    staging_ahead = staging_ok and (
        prod is None
        or prod.status != LexiconPublishRun.Status.SUCCEEDED
        or (staging.finished_at and prod.finished_at and staging.finished_at >= prod.finished_at)
    )
    return {
        "targets": [
            {
                "name": target,
                "label": target.capitalize(),
                "run": latest[target],
                "in_flight": bool(
                    latest[target]
                    and latest[target].status
                    in (LexiconPublishRun.Status.QUEUED, LexiconPublishRun.Status.RUNNING)
                ),
            }
            for target in PUBLISH_TARGETS
        ],
        "staging_ok": staging_ok,
        "staging_ahead": staging_ahead,
    }


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
            # which writer and how it is asked are the row's (env_text): $ARGS is split into words
            f"{backend}/scripts/.venv/bin/python scripts/lexicon_research/${{SCRIPT}} $ARGS",
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


def gemini_folder(writer: LexiconWriter) -> str:
    """Where a writer on Google's plan keeps its entries: one folder a model and effort.

    A folder ``review-*`` that the backend's writers know as written for the dictionary
    (``--for-dictionary``): no ingest reads it yet, and no other writer buys its words again.
    """

    short = writer.model.removeprefix("gemini-4-").removeprefix("claude-").removesuffix("-5-5")
    return f"review-writer-agy-{short}-{writer.effort}-healthy"


def env_text(writer: LexiconWriter) -> str:
    home = Path.home()
    if writer.account == GEMINI_ACCOUNT:
        # the CLI has no meter a writer could pause on: it waits at the plan's wall instead
        return "\n".join(
            [
                "SCRIPT=seat_writer.py",
                f"ARGS=--seat agy:{writer.model}:{writer.effort} --headwords {writer.word_list}"
                f" --langs {writer.language} --out {gemini_folder(writer)} --for-dictionary"
                f" --workers {writer.workers} --budget-usd 100000",
                "",
            ]
        )
    return "\n".join(
        [
            f"CLAUDE_CONFIG_DIR={home / writer.account}",
            "SCRIPT=claude_code_writer.py",
            f"ARGS=--model {writer.model} --effort {writer.effort} --langs {writer.language}"
            f" --headwords {writer.word_list} --workers {writer.workers}"
            f" --pause-session {writer.pause_at_percent}",
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
    """Make the host's writer services match the page; what was done, one line each.

    A writer whose account is paused in the AI panel (manually or at its week/session
    limit) is stopped while the pause holds, and started again once the account is resumed.
    """

    from almonium_book_processor.catalog.models import PlanAccountPause
    from almonium_book_processor.catalog.plan_pause import archived_accounts

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
    paused = set(PlanAccountPause.objects.values_list("provider", "account"))
    archived = archived_accounts()
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
        key = (provider_of(writer.account), writer.account)
        account_archived = key in archived
        account_paused = key in paused
        if writer.running and not account_paused and not account_archived:
            if state == "inactive" and last == "done":
                # the list is written: nothing to start again
                writer.running = False
                state = "finished"
                done.append(f"{unit}: finished its list")
            elif state not in ("active", "activating") or changed:
                _systemctl(runner, "restart" if changed and state == "active" else "start", unit)
                state = _state(runner, unit)
                done.append(f"{unit}: started ({state})")
        else:
            if state in ("active", "activating"):
                _systemctl(runner, "stop", unit)
                state = _state(runner, unit)
                if writer.running and account_archived:
                    reason = " (account archived)"
                elif writer.running and account_paused:
                    reason = " (account paused)"
                else:
                    reason = ""
                done.append(f"{unit}: stopped{reason}")
            if writer.running and account_archived:
                state = "account archived"
            elif writer.running and account_paused:
                state = "account paused"
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
    done.extend(reconcile_publishes(runner=runner))
    return done


def _target_env() -> dict[str, str]:
    """Read host-side target URLs and secrets from ~/.config/almonium/lexicon-targets.env."""

    path = Path.home() / ".config" / "almonium" / "lexicon-targets.env"
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        values[key.strip()] = val.strip().strip('"').strip("'")
    return values


def _target_config(target: str) -> tuple[str, str]:
    """Return ``(backend_url, secret)`` for ``target``; local may omit secret (.env fallback)."""

    env = {**_target_env(), **os.environ}
    prefix = f"LEXICON_{target.upper()}"
    url = env.get(f"{prefix}_URL", "").strip()
    secret = env.get(f"{prefix}_SECRET", "").strip()
    if target == LexiconPublishRun.Target.LOCAL and not url:
        url = DEFAULT_LOCAL_BACKEND_URL
    if not url:
        raise ValueError(
            f"Configure {prefix}_URL (and {prefix}_SECRET) in "
            "~/.config/almonium/lexicon-targets.env on the host."
        )
    if target != LexiconPublishRun.Target.LOCAL and not secret:
        raise ValueError(
            f"Configure {prefix}_SECRET in ~/.config/almonium/lexicon-targets.env on the host."
        )
    return url, secret


def _parse_publish_counts(output: str) -> tuple[int, int, str]:
    import re

    lines = [line.strip() for line in output.splitlines() if line.strip()]
    last_line = lines[-1][:300] if lines else ""
    accepted = rejected = 0
    for line in reversed(lines):
        match = re.search(r"(\d+)\s+accepted,\s+(\d+)\s+rejected", line)
        if match:
            accepted, rejected = int(match.group(1)), int(match.group(2))
            break
    return accepted, rejected, last_line


def _parse_clip_sync_count(output: str) -> int:
    import re

    total = 0
    for line in output.splitlines():
        match = re.match(r"^\|\s*[a-z]{2}\s*\|\s*\d+\s*\|\s*(\d+)\s*\|", line.strip())
        if match:
            total += int(match.group(1))
    return total


def reconcile_publishes(*, runner: Runner = subprocess.run) -> list[str]:
    """Run the oldest queued LexiconPublishRun: ingest_v4, publish_entries, then cached audio."""

    if LexiconPublishRun.objects.filter(status=LexiconPublishRun.Status.RUNNING).exists():
        return []
    run = (
        LexiconPublishRun.objects.filter(status=LexiconPublishRun.Status.QUEUED)
        .order_by("created_at")
        .first()
    )
    if run is None:
        return []
    run.status = LexiconPublishRun.Status.RUNNING
    run.started_at = timezone.now()
    run.error = ""
    run.save(update_fields=["status", "started_at", "error", "updated_at"])

    backend = backend_dir()
    python = str(backend / "scripts" / ".venv" / "bin" / "python")
    langs_args = ["--langs", run.languages] if run.languages else []
    try:
        url, secret = _target_config(run.target)
        ingest = runner(
            [python, "scripts/lexicon_research/ingest_v4.py", *langs_args],
            cwd=backend,
            capture_output=True,
            text=True,
            check=False,
        )
        if ingest.returncode != 0:
            detail = (ingest.stderr or ingest.stdout or "ingest_v4.py failed").strip()
            raise RuntimeError(f"ingest_v4.py failed: {detail[-500:]}")
        env = dict(os.environ)
        if secret:
            env["ALMONIUM_BOOKS_PUBLISHER_SECRET"] = secret
        publish = runner(
            [
                python,
                "scripts/lexicon_research/publish_entries.py",
                "--backend",
                url,
                *langs_args,
            ],
            cwd=backend,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        combined = f"{publish.stdout or ''}\n{publish.stderr or ''}"
        accepted, rejected, last_line = _parse_publish_counts(combined)
        run.accepted = accepted
        run.rejected = rejected
        run.last_line = last_line
        if publish.returncode != 0:
            run.status = LexiconPublishRun.Status.FAILED
            run.error = combined.strip()[-1000:]
            note = (
                f"lexicon publish -> {run.target}: failed "
                f"({accepted} accepted, {rejected} rejected)"
            )
        else:
            target_langs = (
                [lang.strip() for lang in run.languages.split(",") if lang.strip()]
                if run.languages
                else list(LANGUAGES)
            )
            audio_langs = [lang for lang in target_langs if lang in VOICED_LANGUAGES]
            audio_dir = backend / "scripts" / "lexicon_research" / "out" / "audio"
            clips_synced = 0
            if audio_langs and audio_dir.is_dir():
                clips = runner(
                    [
                        python,
                        "scripts/lexicon_research/render_clips.py",
                        "--cached-only",
                        "--backend",
                        url,
                        "--langs",
                        ",".join(audio_langs),
                    ],
                    cwd=backend,
                    env=env,
                    capture_output=True,
                    text=True,
                    check=False,
                )
                clips_out = f"{clips.stdout or ''}\n{clips.stderr or ''}"
                if clips.returncode != 0:
                    raise RuntimeError(
                        f"render_clips.py --cached-only failed: {clips_out.strip()[-500:]}"
                    )
                clips_synced = _parse_clip_sync_count(clips_out)
            run.status = LexiconPublishRun.Status.SUCCEEDED
            audio_note = f", {clips_synced} cached clips synced" if clips_synced else ""
            if audio_note:
                run.last_line = f"{last_line}{audio_note}"[:300]
            note = (
                f"lexicon publish -> {run.target}: {accepted} accepted, {rejected} rejected"
                f"{audio_note}"
            )
    except Exception as error:
        run.status = LexiconPublishRun.Status.FAILED
        run.error = str(error)[:1000]
        run.last_line = str(error)[:300]
        note = f"lexicon publish -> {run.target}: failed ({error})"
    run.finished_at = timezone.now()
    run.save(
        update_fields=[
            "status",
            "accepted",
            "rejected",
            "last_line",
            "error",
            "finished_at",
            "updated_at",
        ]
    )
    return [note]
