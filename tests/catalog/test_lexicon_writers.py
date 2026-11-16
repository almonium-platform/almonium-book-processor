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
    with pytest.raises(ValueError, match="Claude accounts"):
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
    assert "WORD_LIST=en-deep" in env and "WORKERS=4" in env
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
