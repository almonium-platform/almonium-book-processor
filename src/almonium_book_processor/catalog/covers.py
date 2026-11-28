"""Cover art for a published work, chosen on a plan.

Almonium keeps one cover per work: a public-domain picture from Wikimedia Commons, printed in
the book's ink. Which files a work may be given is Almonium's decision (its licence rule and
its search of Commons live there, behind ``/internal/covers``); which of them is the cover is
decided here, because the eye is a vision model on the owner's plan and the plan's CLI is
signed in on this machine.

For one work: Almonium's candidates are laid out on numbered contact sheets of twelve, a
model picks one, and the pick is looked at again on its own at full size before it is
accepted, since a thumbnail hides a caption strip or a page of text and the crop is set from
the real image. A pick that fails the second look is struck out and the sheets asked again,
twice at most. A book with no usable picture of its own gets a second chance: the model
proposes what to search Commons for (its setting, its era, a motif) and chooses among the
period pictures Almonium clears. A work with nothing good is recorded as such and keeps its
typographic cover.

Every call goes through ``outside_calls.ask``: on the judge's seat, under the owner's cap and
paused accounts, recorded in the ledger and found again by content, so a work looked at twice
buys nothing twice. A held call (a cap, a pause, a plan's limit) raises ``Held``: the work
stays pending and is taken again by the next publication or ``manage.py choose_covers``.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import tempfile
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from django.conf import settings

from almonium_book_processor.ai import gateway
from almonium_book_processor.catalog import outside_calls

CELL, COLUMNS, PER_SHEET = 300, 4, 12
MAX_SHEETS = 4  # Almonium offers up to forty-eight candidates
PICKS = 3  # a pick struck out by the second look is replaced at most twice
# Commons asks automated clients to say who they are
USER_AGENT = "Almonium/1.0 (https://almonium.com)"
TIMEOUT_SECONDS = 300  # Almonium walks a work's Commons categories before it answers
# how long an Almonium that is restarting is waited for: three minutes
RESTART_WAITS, RESTART_WAIT_SECONDS = 12, 15

INSTRUCTIONS = (
    "You choose cover art for a classic book in a reading app. You are shown contact "
    "sheets of numbered candidate images, all already cleared for copyright. Pick the one "
    "that works best as the book's cover, or none.\n\n"
    "A good cover is an illustration, engraving, drawing or painting that shows a scene, "
    "a figure or a place from this book or made for it, and reads clearly when printed "
    "small in one ink. It is a flat scan of the artwork. Prefer a picture with one clear "
    "subject, strong shapes and no lettering over a crowded or faint one, and the work's "
    "best-known illustrator where several are offered.\n\n"
    "Never pick: a title page or any page that is mostly text; a page where a small "
    "picture shares the page with text; a book's binding, spine or cover design; a "
    "portrait or photograph of the author; a photograph of a physical book, a building, a "
    "statue or a museum room; a playbill, theatre or film poster, or anything that is "
    "mostly lettering; a map, diagram or family tree; a film still or anything modern; a "
    "picture made for a different book, including a sequel or another work by the same "
    "author; a scan too dark, faint or damaged to read.\n\n"
    "Each candidate is listed with the Commons category it was found in and its file "
    "name, which often say what it is and which book it belongs to. If no candidate is "
    "good, pick none: a plain typographic cover is better than a wrong picture.\n\n"
    "pick is the number on the image, or 0 for none. reason is one short sentence."
)

SECOND_LOOK = (
    "You check one image that was picked from thumbnails as cover art for a classic book "
    "in a reading app. Look at it at full size and decide whether it may be used.\n\n"
    "It is shown as a square crop, printed small in one ink: a tall image keeps its full "
    "width and a square slice of its height, a wide image keeps its full height and a "
    "square slice of its width. You choose where that slice sits.\n\n"
    "Acceptable: an illustration, engraving, drawing or painting of a scene, a figure or "
    "a place from this book, where a square crop exists that shows the subject and no "
    "lettering.\n\n"
    "Not acceptable: a page that is mostly text; a title page; a book's binding or cover "
    "design; a playbill or poster; a portrait or photograph of the author; a photograph "
    "of an object or a place; an image whose subject cannot be shown in a square crop "
    "without a caption, a title or other lettering inside it; a scan too dark, faint or "
    "damaged to read small; a picture that plainly belongs to a different book.\n\n"
    "focus_x and focus_y give the centre of the square crop as a percentage from the "
    "image's left edge and from its top edge; set them so the main subject is inside the "
    "crop and any caption or margin lettering is outside it. reason is one short "
    "sentence."
)

QUERIES = (
    "You help find public-domain cover art on Wikimedia Commons for a classic book that "
    "has no usable illustrations of its own there. Give six short search queries (two to "
    "five words each) for period paintings, engravings, drawings or old photographs that "
    "would suit its cover: the story's setting (the city, the landscape, the kind of "
    "building or room), its era, a central object, animal or kind of figure. Use concrete "
    "nouns and place names, in English or the book's own language; add a word such as "
    "painting, engraving or a decade where it helps. Vary the queries. Do not use the "
    "author's name or the book's title."
)

FITTING = (
    "You choose cover art for a classic book in a reading app. The book has no usable "
    "illustrations of its own, so you are shown contact sheets of numbered period "
    "pictures found by searching for its setting and motifs, all already cleared for "
    "copyright. Pick the one that best suits the book's cover, or none.\n\n"
    "A good cover here is a painting, engraving, drawing or old photograph, made in or "
    "before the book's own time, that a reader of the book would recognise as its world: "
    "the place it is set in, the kind of scene or figure at its heart, its mood. It has "
    "one clear subject and strong shapes, and reads clearly when printed small in one "
    "ink.\n\n"
    "Never pick: anything with lettering in it; a page of text; a portrait of the author "
    "or of any named real person; a map or diagram; a modern photograph or anything made "
    "well after the book; a picture whose link to the book is only a word in its file "
    "name; a picture that would mislead about what the book is; a scan too dark, faint or "
    "damaged.\n\n"
    "Each candidate is listed with the search it came from and its file name. If none "
    "truly suits the book, pick none: a plain typographic cover is better than a picture "
    "that does not belong.\n\n"
    "pick is the number on the image, or 0 for none. reason is one short sentence saying "
    "what the picture shows and why it suits the book."
)

FITTING_LOOK = (
    "You check one period picture that was picked from thumbnails as cover art for a "
    "classic book in a reading app. It was not made for the book; it was chosen because "
    "it suits the book's setting or subject. Look at it at full size and decide whether "
    "it may be used.\n\n"
    "It is shown as a square crop, printed small in one ink: a tall image keeps its full "
    "width and a square slice of its height, a wide image keeps its full height and a "
    "square slice of its width. You choose where that slice sits.\n\n"
    "Acceptable: a painting, engraving, drawing or old photograph from the book's time or "
    "earlier that a reader would recognise as the book's world, where a square crop "
    "exists that shows the subject and no lettering.\n\n"
    "Not acceptable: anything modern; a page of text; a portrait of a named real person; "
    "a map or diagram; an image whose subject cannot be shown in a square crop without a "
    "caption or other lettering inside it; a scan too dark, faint or damaged to read "
    "small; a picture that does not in fact suit this book.\n\n"
    "focus_x and focus_y give the centre of the square crop as a percentage from the "
    "image's left edge and from its top edge; set them so the main subject is inside the "
    "crop and any caption or margin lettering is outside it. reason is one short "
    "sentence."
)

PICK_SCHEMA = {
    "type": "object",
    "required": ["pick", "reason"],
    "additionalProperties": False,
    "properties": {"pick": {"type": "integer", "minimum": 0}, "reason": {"type": "string"}},
}
LOOK_SCHEMA = {
    "type": "object",
    "required": ["acceptable", "focus_x", "focus_y", "reason"],
    "additionalProperties": False,
    "properties": {
        "acceptable": {"type": "boolean"},
        "focus_x": {"type": "integer", "minimum": 0, "maximum": 100},
        "focus_y": {"type": "integer", "minimum": 0, "maximum": 100},
        "reason": {"type": "string"},
    },
}
QUERIES_SCHEMA = {
    "type": "object",
    "required": ["queries"],
    "additionalProperties": False,
    "properties": {
        "queries": {"type": "array", "minItems": 1, "maxItems": 6, "items": {"type": "string"}}
    },
}


class Held(RuntimeError):
    """The gateway refused before anything was paid: the work stays pending."""


class CoverError(RuntimeError):
    """Almonium or the model could not be asked, or answered something unusable."""


def judge_here() -> bool:
    """Whether this environment has the plan the cover judge sits on."""

    seat = gateway.route(settings.COVER_JUDGE)
    return seat.on_plan and not gateway.unavailable(seat)


def almonium(
    path: str,
    payload: dict[str, Any],
    *,
    method: str = "POST",
    pause: Callable[[float], None] = time.sleep,
) -> Any:
    """One signed request to Almonium's cover surface."""

    api_url = os.getenv("ALMONIUM_API_URL", "").rstrip("/")
    token = os.getenv("ALMONIUM_BOOKS_PUBLISHER_SECRET", "")
    if not api_url or not token:
        raise CoverError("Almonium is not configured (ALMONIUM_API_URL and the publisher secret).")
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()
    for attempt in range(RESTART_WAITS + 1):
        # signed afresh each time: a signature is good for five minutes
        timestamp = str(int(time.time()))
        signature = hmac.new(token.encode(), f"{timestamp}.".encode() + body, hashlib.sha256)
        request = Request(
            f"{api_url}/internal/covers{path}",
            data=body,
            headers={
                "Content-Type": "application/json",
                "X-Almonium-Books-Timestamp": timestamp,
                "X-Almonium-Books-Signature": signature.hexdigest(),
            },
            method=method,
        )
        try:
            with urlopen(request, timeout=TIMEOUT_SECONDS) as response:  # noqa: S310
                return json.loads(response.read())
        except HTTPError as error:
            if error.code in (502, 503, 504) and attempt < RESTART_WAITS:
                pause(RESTART_WAIT_SECONDS)
                continue
            detail = error.read().decode("utf-8", errors="replace")[:300]
            raise CoverError(
                f"Almonium answered {path} with HTTP {error.code}: {detail}"
            ) from error
        except json.JSONDecodeError as error:
            raise CoverError(f"Almonium answered {path} with something unreadable") from error
        except (URLError, TimeoutError, ConnectionError) as error:
            # Almonium restarting under the run (a deploy, a rebuild): an answer already paid
            # for must not be lost to that, so the request waits for it to come back
            if attempt == RESTART_WAITS:
                raise CoverError(f"Almonium could not be asked {path}: {error}") from error
            pause(RESTART_WAIT_SECONDS)
    raise CoverError(f"Almonium could not be asked {path}")


def pending() -> list[str]:
    """The works Almonium has never had a cover decided for."""

    return almonium("/pending", {})


def every_work() -> list[str]:
    return almonium("/works", {})


def contact_sheets(candidates: list[dict], folder: Path) -> tuple[list[Path], list[dict]]:
    """The candidates that could be fetched, numbered across sheets of twelve.

    Returns the sheets and the candidates shown, each with the path of its own file for the
    second look. One file Commons will not serve must not lose the work its other candidates.
    """

    from PIL import Image, ImageDraw, ImageFont  # the host worker's; nothing else here draws

    try:
        font = ImageFont.truetype("DejaVuSans-Bold.ttf", 34)
    except OSError:
        font = ImageFont.load_default()
    thumbs, shown = [], []
    for candidate in candidates[: MAX_SHEETS * PER_SHEET]:
        suffix = "png" if candidate["mime"] == "image/png" else "jpg"
        path = folder / f"candidate-{len(shown) + 1}.{suffix}"
        try:
            fetch = Request(candidate["imageUrl"], headers={"User-Agent": USER_AGENT})
            with urlopen(fetch, timeout=60) as response:  # noqa: S310 - a Commons file
                path.write_bytes(response.read())
            thumb = Image.open(path).convert("RGB")
            thumb.thumbnail((CELL - 8, CELL - 8))
        except Exception:  # noqa: BLE001, S112 - any one file may be unreadable
            continue
        thumbs.append(thumb)
        shown.append({**candidate, "file": str(path)})
        time.sleep(0.2)
    sheets = []
    for start in range(0, len(shown), PER_SHEET):
        page = thumbs[start : start + PER_SHEET]
        rows = (len(page) + COLUMNS - 1) // COLUMNS
        sheet = Image.new("RGB", (COLUMNS * CELL, rows * CELL), "white")
        draw = ImageDraw.Draw(sheet)
        for index, thumb in enumerate(page):
            x, y = (index % COLUMNS) * CELL, (index // COLUMNS) * CELL
            sheet.paste(thumb, (x + (CELL - thumb.width) // 2, y + (CELL - thumb.height) // 2))
            label = str(start + index + 1)
            draw.rectangle([x, y, x + 30 + 22 * len(label), y + 44], fill="black")
            draw.text((x + 8, y + 3), label, fill="white", font=font)
        target = folder / f"sheet-{len(sheets) + 1}.jpg"
        sheet.save(target, quality=80)
        sheets.append(target)
    return sheets, shown


def _ask(purpose: str, instructions: str, said: str, schema: dict, images: list[str]) -> dict:
    """One call through the gateway: the answer, with what the gateway recorded as its cost."""

    answered = outside_calls.ask(
        {
            "seat": settings.COVER_JUDGE,
            "purpose": purpose,
            "caller": "covers",
            "instructions": instructions,
            "input": said,
            "schema": schema,
            **({"images": images} if images else {}),
        }
    )
    if answered["status"] == "held":
        raise Held(str(answered.get("reason"))[:300])
    if answered["status"] != "completed":
        raise CoverError(str(answered.get("error"))[:300])
    return {
        **json.loads(answered["text"]),
        "_cost": answered.get("cost_usd") or 0.0,
        "_model": f"{answered.get('provider')}:{answered.get('model')}"[:120],
    }


def _judged(offered: dict, folder: Path, instructions: str, look: str, sheets_of) -> dict:
    """One round of picking from what was offered: the candidate chosen or None, the crop,
    the reasons, the cost and the model."""

    result = {"chosen": None, "focus": (50, 50), "notes": [], "cost": 0.0, "model": None}
    folder.mkdir(parents=True, exist_ok=True)
    sheets, shown = sheets_of(offered["candidates"], folder)
    if not sheets:
        return {**result, "notes": ["No candidate could be downloaded."]}
    book = f'The book: "{offered["title"]}" by {offered["author"]}.'
    listed = "\n".join(
        f"{number}. [{candidate.get('foundIn') or 'no category'}] {candidate['title']}"
        for number, candidate in enumerate(shown, 1)
    )
    struck: set[int] = set()
    for _ in range(PICKS):
        barred = (
            "\nThese were looked at closely and rejected; do not pick them: "
            f"{', '.join(str(number) for number in sorted(struck))}."
            if struck
            else ""
        )
        verdict = _ask(
            "cover_choice",
            instructions,
            f"{book} The sheets show {len(shown)} candidates, numbered across the sheets:"
            f"\n{listed}{barred}",
            PICK_SCHEMA,
            [str(sheet) for sheet in sheets],
        )
        result["cost"] += verdict["_cost"]
        result["model"] = verdict["_model"]
        number = verdict["pick"]
        if not 1 <= number <= len(shown) or number in struck:
            result["notes"].append(verdict["reason"])
            return result
        candidate = shown[number - 1]
        checked = _ask(
            "cover_check",
            look,
            f"{book} The image's file name on Commons: {candidate['title']}. "
            f"Found in: {candidate.get('foundIn') or 'no category'}.",
            LOOK_SCHEMA,
            [candidate["file"]],
        )
        result["cost"] += checked["_cost"]
        if checked["acceptable"]:
            chosen = {key: value for key, value in candidate.items() if key != "file"}
            return {
                **result,
                "chosen": chosen,
                "focus": (checked["focus_x"], checked["focus_y"]),
                "notes": [verdict["reason"]],
            }
        struck.add(number)
        result["notes"].append(f"{number} rejected at full size: {checked['reason']}")
    return result


def choose_cover(
    work_slug: str,
    *,
    sheets_of: Callable[[list[dict], Path], tuple[list[Path], list[dict]]] = contact_sheets,
) -> dict[str, Any]:
    """Decide one work's cover and tell Almonium: ``{"status", "reason", "cost_usd"}``.

    First among the pictures made for the book; when there are none, or none is good, among
    period pictures that suit it. ``Held`` when the gateway refuses; nothing is recorded then.
    """

    offered = almonium("/candidates", {"workSlug": work_slug})
    decision = {
        "workSlug": work_slug,
        "chosen": None,
        "focusX": 50,
        "focusY": 50,
        "reason": offered["note"],
        "model": None,
    }
    notes = [offered["note"]] if offered["note"] else []
    cost = 0.0
    with tempfile.TemporaryDirectory(prefix="almonium-covers-") as folder:
        if offered["candidates"]:
            own = _judged(offered, Path(folder, "own"), INSTRUCTIONS, SECOND_LOOK, sheets_of)
            cost += own["cost"]
            notes = own["notes"]
            decision["model"] = own["model"]
            if own["chosen"]:
                decision.update(
                    chosen=own["chosen"],
                    focusX=own["focus"][0],
                    focusY=own["focus"][1],
                    reason=own["notes"][0][:1000],
                )
        if not decision["chosen"]:
            proposed = _ask(
                "cover_queries",
                QUERIES,
                f'The book: "{offered["title"]}" by {offered["author"]}.',
                QUERIES_SCHEMA,
                [],
            )
            cost += proposed["_cost"]
            fitting = almonium(
                "/fitting", {"workSlug": work_slug, "queries": proposed["queries"][:6]}
            )
            if fitting["candidates"]:
                suited = _judged(fitting, Path(folder, "fitting"), FITTING, FITTING_LOOK, sheets_of)
                cost += suited["cost"]
                decision["model"] = suited["model"] or decision["model"]
                if suited["chosen"]:
                    decision.update(
                        chosen=suited["chosen"],
                        focusX=suited["focus"][0],
                        focusY=suited["focus"][1],
                        reason=("Not made for the book. " + suited["notes"][0])[:1000],
                    )
                else:
                    notes += suited["notes"]
            else:
                notes.append(fitting["note"])
    if not decision["chosen"]:
        decision["reason"] = " ".join(note for note in notes if note)[:1000]
    status = almonium("/decisions", decision, method="PUT")["status"]
    return {"status": status, "reason": decision["reason"] or "", "cost_usd": cost}
