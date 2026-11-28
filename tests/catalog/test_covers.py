"""A work's cover: chosen among what Almonium clears, looked at twice, bought once."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from almonium_book_processor.catalog import covers, tasks

FRONTISPIECE = {
    "title": "File:Frontispiece 1831.jpg",
    "pageUrl": "https://commons.wikimedia.org/wiki/File:Frontispiece_1831.jpg",
    "imageUrl": "https://upload.wikimedia.org/f.jpg",
    "mime": "image/jpeg",
    "artist": "Theodor von Holst",
    "licence": "Public domain",
    "licenceBasis": "PD Old",
    "foundIn": "Frankenstein",
}
TITLE_PAGE = {
    **FRONTISPIECE,
    "title": "File:Title page.jpg",
    "imageUrl": "https://upload.wikimedia.org/t.jpg",
}
BRIDGE = {**FRONTISPIECE, "title": "File:Geneva lake 1820.jpg", "foundIn": "Search: Geneva lake"}


@pytest.fixture(autouse=True)
def plans(settings):
    settings.AI_PLANS = "codex,claude-code,antigravity"


def sheets_of(candidates, folder):
    return [folder / "sheet-1.jpg"], [
        {**candidate, "file": str(folder / f"candidate-{number}.jpg")}
        for number, candidate in enumerate(candidates, 1)
    ]


class Almonium:
    """What Almonium answers, and what it was told."""

    def __init__(self, own, fitting=()):
        self.own, self.fitting, self.calls = list(own), list(fitting), []

    def __call__(self, path, payload, *, method="POST"):
        self.calls.append((path, payload))
        offered = {"workSlug": "frankenstein", "title": "Frankenstein", "author": "Mary Shelley"}
        if path == "/candidates":
            note = "" if self.own else "No file on Commons passed the licence rule."
            return {**offered, "candidates": self.own, "note": note}
        if path == "/fitting":
            return {**offered, "candidates": self.fitting, "note": ""}
        if path == "/decisions":
            return {"status": "APPROVED" if payload["chosen"] else "NONE"}
        return ["frankenstein"]

    @property
    def decision(self):
        return next(payload for path, payload in self.calls if path == "/decisions")


def gateway_saying(monkeypatch, *answers):
    """The gateway answers in turn; a string answer is a hold."""

    asked, left = [], list(answers)

    def ask(request):
        asked.append(request)
        answer = left.pop(0)
        if isinstance(answer, str):
            return {"status": "held", "reason": answer}
        return {
            "status": "completed",
            "text": json.dumps(answer),
            "cost_usd": 0.01,
            "provider": "claude-code",
            "model": "claude-sonnet-5-5",
        }

    monkeypatch.setattr(covers.outside_calls, "ask", ask)
    return asked


def test_a_pick_that_fails_the_second_look_is_struck_out_and_the_sheets_asked_again(monkeypatch):
    almonium = Almonium([TITLE_PAGE, FRONTISPIECE])
    monkeypatch.setattr(covers, "almonium", almonium)
    asked = gateway_saying(
        monkeypatch,
        {"pick": 1, "reason": "A clear picture."},
        {"acceptable": False, "focus_x": 50, "focus_y": 50, "reason": "It is a page of text."},
        {"pick": 2, "reason": "The creature and its maker."},
        {"acceptable": True, "focus_x": 45, "focus_y": 20, "reason": "A clean engraving."},
    )

    said = covers.choose_cover("frankenstein", sheets_of=sheets_of)

    assert said["status"] == "APPROVED" and said["cost_usd"] == pytest.approx(0.04)
    decision = almonium.decision
    assert decision["chosen"] == FRONTISPIECE and "file" not in decision["chosen"]
    assert (decision["focusX"], decision["focusY"]) == (45, 20)
    assert decision["reason"] == "The creature and its maker."
    # the sheets go to the pick, the one picked file to the second look
    assert asked[0]["images"][0].endswith("sheet-1.jpg") and asked[0]["purpose"] == "cover_choice"
    assert (
        asked[1]["images"][0].endswith("candidate-1.jpg") and asked[1]["purpose"] == "cover_check"
    )
    assert "do not pick them: 1." in asked[2]["input"]
    assert all(request["seat"] == "claude-code:claude-sonnet-5-5:low" for request in asked)


def test_a_book_with_no_picture_of_its_own_is_given_one_that_suits_it_and_the_record_says_so(
    monkeypatch,
):
    almonium = Almonium([], fitting=[BRIDGE])
    monkeypatch.setattr(covers, "almonium", almonium)
    asked = gateway_saying(
        monkeypatch,
        {"queries": ["Geneva lake engraving", "Alps glacier 1820"]},
        {"pick": 1, "reason": "The lake the story begins on."},
        {"acceptable": True, "focus_x": 50, "focus_y": 60, "reason": "A period view."},
    )

    said = covers.choose_cover("frankenstein", sheets_of=sheets_of)

    assert said["status"] == "APPROVED"
    assert (
        "/fitting",
        {"workSlug": "frankenstein", "queries": ["Geneva lake engraving", "Alps glacier 1820"]},
    ) in almonium.calls
    assert almonium.decision["reason"] == "Not made for the book. The lake the story begins on."
    assert asked[0]["purpose"] == "cover_queries" and "images" not in asked[0]
    assert (
        asked[1]["instructions"] == covers.FITTING
        and asked[2]["instructions"] == covers.FITTING_LOOK
    )


def test_nothing_good_anywhere_is_recorded_as_such(monkeypatch):
    almonium = Almonium([TITLE_PAGE], fitting=[])
    monkeypatch.setattr(covers, "almonium", almonium)
    gateway_saying(
        monkeypatch,
        {"pick": 0, "reason": "Only a title page."},
        {"queries": ["Geneva lake engraving"]},
    )

    said = covers.choose_cover("frankenstein", sheets_of=sheets_of)

    assert said["status"] == "NONE" and almonium.decision["chosen"] is None
    assert almonium.decision["reason"].startswith("Only a title page.")


def test_a_held_call_records_nothing_and_leaves_the_work_pending(monkeypatch):
    almonium = Almonium([FRONTISPIECE])
    monkeypatch.setattr(covers, "almonium", almonium)
    gateway_saying(monkeypatch, "Allowance used up")

    with pytest.raises(covers.Held, match="Allowance used up"):
        covers.choose_cover("frankenstein", sheets_of=sheets_of)

    assert not [path for path, _ in almonium.calls if path == "/decisions"]


def edition(owner_id=None):
    return SimpleNamespace(work=SimpleNamespace(owner_id=owner_id, slug="frankenstein"))


def test_a_published_public_work_has_its_cover_looked_for_where_the_plan_is(monkeypatch, settings):
    queued = []
    monkeypatch.setattr(tasks.choose_work_cover, "delay", queued.append)

    tasks.queue_cover_choice(edition())
    assert queued == ["frankenstein"]

    tasks.queue_cover_choice(edition(owner_id="01989f47-4c2a-7a10-9e5b-751983624a30"))
    settings.AI_PLANS = ""
    tasks.queue_cover_choice(edition())
    assert queued == ["frankenstein"]


def test_a_work_already_decided_is_not_looked_at_again_and_a_hold_is_not_a_failure(monkeypatch):
    chosen = []
    monkeypatch.setattr(covers, "pending", lambda: ["dracula"])
    monkeypatch.setattr(
        covers, "choose_cover", lambda slug: chosen.append(slug) or {"status": "NONE", "reason": ""}
    )

    tasks.choose_work_cover.run("frankenstein")
    tasks.choose_work_cover.run("dracula")
    assert chosen == ["dracula"]

    def held(slug):
        raise covers.Held("Allowance used up")

    monkeypatch.setattr(covers, "choose_cover", held)
    tasks.choose_work_cover.run("dracula")
