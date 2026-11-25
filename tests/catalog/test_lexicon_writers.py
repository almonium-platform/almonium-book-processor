"""Entry writers are set up and switched on the Operations page and run by the host's timer."""

from __future__ import annotations

import subprocess

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from almonium_book_processor.catalog import lexicon_writers
from almonium_book_processor.catalog.models import LexiconWriter

pytestmark = pytest.mark.django_db


@pytest.fixture
def accounts(settings):
    settings.CLAUDE_CONFIG_DIRS = ["/home/me/.claude", "/home/me/.claude-2"]


def _add(**overrides):
    fields = {
        "account": ".claude-2",
        "language": "en",
        "word_list": "en-deep",
        "workers": 4,
        "pause_at_percent": 100,
        "model": "claude-opus-5-5",
        "effort": "high",
        "by": "editor",
        **overrides,
    }
    return lexicon_writers.add_writer(**fields)


def test_a_writer_is_added_off_and_checked(accounts):
    writer = _add()
    assert not writer.running and writer.account == ".claude-2"

    with pytest.raises(ValueError, match="bridge language"):
        _add(language="uk", word_list="v4-new")
    with pytest.raises(ValueError, match="would write the same words"):
        _add(account=".claude")
    with pytest.raises(ValueError, match="one of the accounts"):
        _add(account=".codex", word_list="other")
    with pytest.raises(ValueError, match="list"):
        _add(word_list="../etc/passwd")


def test_the_page_adds_starts_pauses_and_removes_a_writer(client, accounts):
    user = get_user_model().objects.create_user("editor", password="x", is_staff=True)
    client.force_login(user)
    url = reverse("catalog:lexicon-writer")

    client.post(
        url,
        {
            "action": "add",
            "account": ".claude-2",
            "language": "de",
            "word_list": "v4-new",
            "workers": "2",
            "pause_at_percent": "90",
            "model": "claude-opus-5-5",
            "effort": "high",
            "start": "1",
        },
    )
    writer = LexiconWriter.objects.get()
    assert writer.running and writer.pause_at_percent == 90

    client.post(url, {"action": "pause", "writer": writer.id})
    writer.refresh_from_db()
    assert not writer.running

    page = client.get(reverse("catalog:operations"), {"show": "entries"}).content.decode()
    assert "v4-new" in page and "Start" in page

    client.post(url, {"action": "remove", "writer": writer.id})
    assert not LexiconWriter.objects.exists()


def test_only_staff_may_switch_writers(client):
    assert client.post(reverse("catalog:lexicon-writer"), {"action": "add"}).status_code == 302
    assert not LexiconWriter.objects.exists()


class FakeSystemd:
    """systemctl --user as the reconcile calls it, with units that are active or not."""

    def __init__(self, active=(), listed=()):
        self.active = set(active)
        self.listed = set(listed) | set(active)
        self.calls = []

    def __call__(self, command, **kwargs):
        args = command[2:]
        self.calls.append(" ".join(args))
        out = ""
        if args[0] == "is-active":
            out = "active" if args[1] in self.active else "inactive"
        elif args[0] in ("start", "restart"):
            self.active.add(args[1])
            self.listed.add(args[1])
        elif args[0] == "stop":
            self.active.discard(args[1])
        elif args[0] == "list-units":
            out = "\n".join(f"{unit} loaded active running x" for unit in sorted(self.listed))
        return subprocess.CompletedProcess(command, 0, stdout=out, stderr="")


@pytest.fixture
def host(tmp_path, monkeypatch, settings, accounts):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    backend = tmp_path / "almonium-be"
    (backend / "scripts" / "lexicon_research" / "out" / "logs").mkdir(parents=True)
    settings.LEXICON_BACKEND_DIR = str(backend)
    return tmp_path


def test_the_host_starts_a_writer_that_is_on_and_reports_it(host):
    writer = _add()
    lexicon_writers.set_running(writer, True, by="editor")
    systemd = FakeSystemd()

    done = lexicon_writers.reconcile(runner=systemd)

    unit = f"almonium-lexicon-writer@{writer.id}.service"
    assert f"start {unit}" in systemd.calls
    assert any(line.startswith(unit) for line in done)
    env = (host / "home" / ".config" / "almonium" / f"lexicon-writer-{writer.id}.env").read_text()
    assert "CLAUDE_CONFIG_DIR=" in env and env.count(".claude-2") == 1
    assert "SCRIPT=claude_code_writer.py" in env
    assert "--headwords en-deep --workers 4 --pause-session" in env
    template = host / "home" / ".config" / "systemd" / "user" / "almonium-lexicon-writer@.service"
    assert "systemd-inhibit --what=sleep:idle" in template.read_text()
    writer.refresh_from_db()
    assert writer.state == "active" and writer.checked_at

    # nothing changed since: the next pass leaves it alone
    systemd.calls.clear()
    lexicon_writers.reconcile(runner=systemd)
    assert not any(call.startswith(("start", "restart", "stop")) for call in systemd.calls)


def test_the_host_stops_a_paused_writer_and_one_removed_from_the_page(host):
    paused = _add()
    stale = "almonium-lexicon-writer@999.service"
    systemd = FakeSystemd(active={f"almonium-lexicon-writer@{paused.id}.service", stale})

    lexicon_writers.reconcile(runner=systemd)

    assert f"stop almonium-lexicon-writer@{paused.id}.service" in systemd.calls
    assert f"stop {stale}" in systemd.calls


def test_a_writer_at_the_end_of_its_list_switches_itself_off(host):
    writer = _add()
    lexicon_writers.set_running(writer, True, by="editor")
    lexicon_writers.log_path(writer.id).write_text(
        "cc-claude-opus-5-5-v4 en zymurgy 1 lexemes\ndone\n"
    )

    lexicon_writers.reconcile(runner=FakeSystemd())

    writer.refresh_from_db()
    assert not writer.running and writer.state == "finished" and writer.last_line == "done"


def test_the_dashboard_has_the_writers_and_its_buttons_come_back_to_it(client, accounts):
    user = get_user_model().objects.create_user("staff", password="x", is_staff=True)
    client.force_login(user)
    writer = LexiconWriter.objects.create(
        account=".claude-2", language="en", word_list="healthy", running=True, state="active"
    )
    LexiconWriter.objects.create(account=".claude", language="de", word_list="healthy")

    page = client.get(reverse("catalog:dashboard")).content.decode()

    assert "Entries · 1 writer on" in page and "· 1 off" in page
    assert 'name="back" value="dashboard"' in page
    response = client.post(
        reverse("catalog:lexicon-writer"),
        {"action": "pause", "writer": writer.id, "back": "dashboard"},
    )
    assert response.url == reverse("catalog:dashboard") + "#entries"
    writer.refresh_from_db()
    assert not writer.running


def test_a_writer_stops_when_its_claude_account_is_paused_and_resumes_when_lifted(host):
    from almonium_book_processor.catalog.models import PlanAccountPause

    writer = _add(account=".claude")
    lexicon_writers.set_running(writer, True, by="editor")
    unit = f"almonium-lexicon-writer@{writer.id}.service"
    systemd = FakeSystemd(active={unit})

    PlanAccountPause.objects.create(provider="claude-code", account=".claude", note="Paused by app")
    done = lexicon_writers.reconcile(runner=systemd)

    assert f"stop {unit}" in systemd.calls
    assert any("account paused" in line for line in done)
    writer.refresh_from_db()
    assert writer.running and writer.state == "account paused"

    # unpausing the account in the AI panel brings the writer back up on the next pass
    systemd.calls.clear()
    PlanAccountPause.objects.filter(provider="claude-code", account=".claude").delete()
    lexicon_writers.reconcile(runner=systemd)

    assert f"start {unit}" in systemd.calls
    writer.refresh_from_db()
    assert writer.running and writer.state == "active"


def test_lexicon_publish_queues_ingests_and_publishes_on_the_host(client, host):
    from almonium_book_processor.catalog.models import LexiconPublishRun

    user = get_user_model().objects.create_user("staff", password="x", is_staff=True)
    client.force_login(user)

    response = client.post(
        reverse("catalog:lexicon-publish"),
        {"target": "staging", "languages": "en", "back": "dashboard"},
    )
    assert response.url == reverse("catalog:dashboard") + "#entries"
    run = LexiconPublishRun.objects.get()
    assert (run.target, run.languages, run.status) == ("staging", "en", "queued")

    # duplicate request while queued is refused
    client.post(
        reverse("catalog:lexicon-publish"),
        {"target": "staging", "languages": "en", "back": "dashboard"},
    )
    assert LexiconPublishRun.objects.count() == 1

    # configure staging target in host-side env file
    cfg = host / "home" / ".config" / "almonium"
    cfg.mkdir(parents=True, exist_ok=True)
    (cfg / "lexicon-targets.env").write_text(
        "LEXICON_STAGING_URL=https://staging.almonium.com/api/v1\n"
        "LEXICON_STAGING_SECRET=super-secret\n",
        encoding="utf-8",
    )

    calls = []

    def fake_runner(command, **kwargs):
        calls.append((command, kwargs.get("env") or {}))
        if command[0] == "systemctl":
            return subprocess.CompletedProcess(command, 0, stdout="", stderr="")
        if "publish_entries.py" in command[1]:
            return subprocess.CompletedProcess(
                command,
                0,
                stdout="42 accepted, 0 rejected (0 whole batches failed) in 3s\n",
                stderr="",
            )
        return subprocess.CompletedProcess(command, 0, stdout="ingested\n", stderr="")

    done = lexicon_writers.reconcile(runner=fake_runner)

    run.refresh_from_db()
    assert run.status == LexiconPublishRun.Status.SUCCEEDED
    assert (run.accepted, run.rejected) == (42, 0)
    assert any("lexicon publish -> staging: 42 accepted, 0 rejected" in line for line in done)
    script_calls = [c for c in calls if c[0][0] != "systemctl"]
    assert len(script_calls) == 2
    assert "ingest_v4.py" in script_calls[0][0][1] and "--langs" in script_calls[0][0]
    assert "publish_entries.py" in script_calls[1][0][1]
    assert "--backend" in script_calls[1][0]
    assert "https://staging.almonium.com/api/v1" in script_calls[1][0]
    assert script_calls[1][1].get("ALMONIUM_BOOKS_PUBLISHER_SECRET") == "super-secret"

    page = client.get(reverse("catalog:dashboard")).content.decode()
    assert "Publish to Staging" in page and "42 accepted" in page


def test_lexicon_publish_syncs_cached_audio_clips_after_publishing(host):
    from almonium_book_processor.catalog.models import LexiconPublishRun

    audio_dir = host / "almonium-be" / "scripts" / "lexicon_research" / "out" / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)
    run = LexiconPublishRun.objects.create(
        target=LexiconPublishRun.Target.LOCAL,
        languages="en,it",
        requested_by="editor",
    )

    calls = []

    def fake_runner(command, **kwargs):
        calls.append((command, kwargs.get("env") or {}))
        if command[0] == "systemctl":
            return subprocess.CompletedProcess(command, 0, stdout="", stderr="")
        if "publish_entries.py" in command[1]:
            return subprocess.CompletedProcess(
                command,
                0,
                stdout="10 accepted, 0 rejected (0 whole batches failed) in 1s\n",
                stderr="",
            )
        if "render_clips.py" in command[1]:
            return subprocess.CompletedProcess(
                command,
                0,
                stdout=(
                    "| Language | Pending | Rendered | Verified |\n"
                    "|---|---|---|---|\n"
                    "| en | 10 | 6 | 6 |\n"
                ),
                stderr="",
            )
        return subprocess.CompletedProcess(command, 0, stdout="ingested\n", stderr="")

    done = lexicon_writers.reconcile(runner=fake_runner)

    run.refresh_from_db()
    assert run.status == LexiconPublishRun.Status.SUCCEEDED
    assert "6 cached clips synced" in run.last_line
    assert any("6 cached clips synced" in line for line in done)
    script_calls = [c[0] for c in calls if c[0][0] != "systemctl"]
    assert len(script_calls) == 3
    assert "render_clips.py" in script_calls[2][1]
    assert "--cached-only" in script_calls[2]
    # "it" has no voice yet, so only "en" is passed to render_clips.py
    assert script_calls[2][script_calls[2].index("--langs") + 1] == "en"


def test_a_writer_on_googles_plan_runs_the_seat_writer_for_the_dictionary(host):
    with pytest.raises(ValueError, match="antigravity-cli serves"):
        _add(
            account="antigravity-cli", language="it", word_list="healthy", model="claude-fable-5-2"
        )
    writer = _add(
        account="antigravity-cli",
        language="it",
        word_list="healthy",
        model="gemini-4-carbon",
        effort="medium",
    )
    lexicon_writers.set_running(writer, True, by="editor")
    systemd = FakeSystemd()

    lexicon_writers.reconcile(runner=systemd)

    assert f"start almonium-lexicon-writer@{writer.id}.service" in systemd.calls
    env = (host / "home" / ".config" / "almonium" / f"lexicon-writer-{writer.id}.env").read_text()
    assert "SCRIPT=seat_writer.py" in env and "CLAUDE_CONFIG_DIR" not in env
    assert "--seat agy:gemini-4-carbon:medium --headwords healthy --langs it" in env
    assert "--out review-writer-agy-carbon-medium-healthy --for-dictionary" in env
    writer.model, writer.effort = "claude-opus-5-5", "high"
    assert lexicon_writers.gemini_folder(writer) == "review-writer-agy-opus-high-healthy"


def test_a_writer_on_googles_plan_stops_while_that_plan_is_paused(host):
    from almonium_book_processor.catalog.models import PlanAccountPause

    writer = _add(
        account="antigravity-cli", language="it", word_list="healthy", model="gemini-4-carbon"
    )
    lexicon_writers.set_running(writer, True, by="editor")
    PlanAccountPause.objects.create(provider="antigravity", account="antigravity-cli")
    systemd = FakeSystemd(active={f"almonium-lexicon-writer@{writer.id}.service"})

    done = lexicon_writers.reconcile(runner=systemd)

    assert any("account paused" in line for line in done)
    writer.refresh_from_db()
    assert writer.state == "account paused" and writer.running
