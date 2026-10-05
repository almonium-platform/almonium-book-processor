"""A book's adaptations made from start to verdict with nobody reading them.

One production takes a source edition and the levels asked for, highest first, and carries
each through the steps a person used to start by hand: the source's levels, the probe, the
book, the judges' reading, the mending of chapters read above the target, the fidelity audit,
the corrections both auditors stand behind, the audit again on what those changed, and a
verdict. A level that passes both gates is signed off and, if asked, promoted; a level that
does not is held with the reasons, and the levels below it are not attempted.

Nothing here decides quality. Each step asks the same gate a person's click would have met,
and the production only knows what to start next, how long to wait, and when to stop trying:
a failed step is started once more, a chapter is mended once by paragraph and once whole,
corrections are applied and re-read twice at most, and a step nobody finishes in three hours
holds the book instead of waiting for ever.

The production is a run on the source edition that a short task moves forward and then asks
to be called again (``tasks.produce_edition``): it holds no worker while the long jobs it
started run on theirs, and it picks up where it was after a restart.
"""

from __future__ import annotations

import uuid
from datetime import timedelta

from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from almonium_book_processor.catalog.models import (
    Edition,
    PipelineRun,
    QAWarning,
)

VERSION = "production-v1"
TICK_SECONDS = 30
# A whole book is written in about half an hour and audited in a quarter.
STEP_TIMEOUT = timedelta(hours=3)
# How often one thing is started before the book is held: the first time and once more.
STARTS = 2
# How often corrections are applied and the changed chapters audited again.
SETTLE_ROUNDS = 2
# A job nobody has touched for this long was left behind by a worker that died. It is not
# waited for: the step starts it again where it can, and other steps stop counting it.
STALL = timedelta(minutes=30)

ACTIVE = (PipelineRun.Status.QUEUED, PipelineRun.Status.RUNNING)
FINISHED = (
    PipelineRun.Status.SUCCEEDED,
    PipelineRun.Status.FAILED,
    PipelineRun.Status.CANCELLED,
)


class Held(Exception):
    """The level cannot go further without a person; the reasons say why."""

    def __init__(self, *reasons: str) -> None:
        super().__init__("; ".join(reasons))
        self.reasons = [reason for reason in reasons if reason]


def backed(evidence: dict) -> bool:
    """Whether more than one model stands behind a finding.

    An adaptation's audit: both auditors raised it, or the other confirmed it when asked.
    A translation's review: both reviewers raised it or the second confirmed it, and where
    an adjudicator ruled, the ruling is to change the text.
    """

    ruling = (evidence.get("adjudication") or {}).get("verdict")
    if ruling:
        return ruling in ("apply_proposed", "new_fix")
    if evidence.get("agreement"):
        return evidence["agreement"] in ("both", "confirmed")
    return len(evidence.get("raised_by") or []) > 1 or bool(
        (evidence.get("second_opinion") or {}).get("material")
    )


def queue_production(
    source_id,
    levels: list[str],
    *,
    sign_off: bool = True,
    promote_to: str = "",
    publish: bool = False,
) -> PipelineRun:
    """Start a production of ``levels`` from a source edition, or return the one under way."""

    from almonium_book_processor.catalog.adaptation_floor import PROBE_LEVELS
    from almonium_book_processor.catalog.chapter_projections import LEVELS
    from almonium_book_processor.catalog.tasks import produce_edition

    levels = sorted(dict.fromkeys(levels), key=LEVELS.index, reverse=True)
    if not levels or any(level not in PROBE_LEVELS for level in levels):
        raise ValueError(f"Choose the levels to produce from {', '.join(PROBE_LEVELS)}.")
    with transaction.atomic():
        source = Edition.objects.select_for_update().select_related("work").get(pk=source_id)
        if source.edition_type == Edition.EditionType.ADAPTATION:
            raise ValueError("Produce from the original edition, not from an adaptation.")
        active = source.pipeline_runs.filter(processor_version=VERSION, status__in=ACTIVE).first()
        if active is not None:
            return active
        run = PipelineRun.objects.create(
            edition=source,
            stage=PipelineRun.Stage.ADAPT,
            processor_version=VERSION,
            input_hash="",
            idempotency_key=f"{source.id}:production:{uuid.uuid4().hex}",
            summary={
                "levels": levels,
                "index": 0,
                "step": "source",
                "since": timezone.now().isoformat(),
                "sign_off": sign_off,
                "promote_to": promote_to,
                "publish": publish,
                "editions": {},
                "starts": {},
                "mended": {},
                "settled": {},
                "outcomes": {},
                "log": [],
            },
        )
        transaction.on_commit(lambda: produce_edition.delay(str(run.id)))
    return run


def advance(run_id) -> bool:
    """Move a production as far as it can go without waiting; say whether it is finished."""

    for _ in range(2 * len(STEPS)):
        finished, moved = _advance_once(run_id)
        if finished or not moved:
            return finished
    return False


def _advance_once(run_id) -> tuple[bool, bool]:
    """One step: whether the production is finished, and whether it moved to another step."""

    run = PipelineRun.objects.select_related("edition__work").get(pk=run_id)
    if run.processor_version != VERSION:
        raise ValueError("Not a production run.")
    if run.status in FINISHED:
        return True, False
    if run.status == PipelineRun.Status.QUEUED:
        run.status = PipelineRun.Status.RUNNING
        run.started_at = timezone.now()
    state = run.summary
    level = state["levels"][state["index"]]
    step = state["step"]
    try:
        move = STEPS[step](run, state, level)
        if move[0] == "wait" and timezone.now() - parse_datetime(state["since"]) > STEP_TIMEOUT:
            raise Held(f"Nothing finished '{step}' in {STEP_TIMEOUT}: {move[1]}")
    except Held as held:
        move = ("hold", held.reasons)
    except Exception as error:
        # a step that breaks is started again on the next call, as often as its own
        # counters allow; one that keeps breaking holds the book with what it said
        try:
            _started(state, f"error:{level}:{step}", STARTS + 1)
            move = ("wait", f"{type(error).__name__}: {str(error)[:300]}; trying again")
        except Held:
            move = ("hold", [f"'{step}' failed: {type(error).__name__}: {str(error)[:300]}"])
    finished = _apply(run, state, level, step, move)
    run.summary = state
    run.save()
    return finished, move[0] in ("goto", "ready")


def _apply(run: PipelineRun, state: dict, level: str, step: str, move: tuple) -> bool:
    kind = move[0]
    if kind == "wait":
        _log(state, level, step, move[1], repeat=False)
        return False
    if kind == "goto":
        _log(state, level, step, move[2])
        state["step"] = move[1]
        state["since"] = timezone.now().isoformat()
        return False
    if kind == "ready":
        state["outcomes"][level] = {"outcome": "ready", "note": move[1]}
        _log(state, level, step, f"READY: {move[1]}")
        if state["index"] + 1 < len(state["levels"]):
            state["index"] += 1
            state["step"] = "probe"
            state["since"] = timezone.now().isoformat()
            return False
        run.status = PipelineRun.Status.SUCCEEDED
    else:
        reasons = move[1]
        state["outcomes"][level] = {"outcome": "held", "reasons": reasons}
        _log(state, level, step, "HELD: " + "; ".join(reasons))
        for skipped in state["levels"][state["index"] + 1 :]:
            state["outcomes"][skipped] = {
                "outcome": "not attempted",
                "reasons": [f"{level}, the level above, was held."],
            }
        # a held book is a verdict, and it is shown where a failed job is: it needs a person
        run.status = PipelineRun.Status.FAILED
        run.error = f"Held at {level}: " + "; ".join(reasons)
    run.progress = 100
    run.finished_at = timezone.now()
    return True


def _log(state: dict, level: str, step: str, note: str, *, repeat: bool = True) -> None:
    entry = {"at": timezone.now().isoformat(), "level": level, "step": step, "note": note}
    last = state["log"][-1] if state["log"] else None
    if not repeat and last and (last["level"], last["step"], last["note"]) == (level, step, note):
        return
    state["log"].append(entry)


def _started(state: dict, key: str, limit: int = STARTS) -> None:
    """Count a start of ``key``; hold the book rather than start it more than ``limit`` times."""

    count = state["starts"].get(key, 0)
    if count >= limit:
        raise Held(f"'{key}' was started {count} times and did not finish.")
    state["starts"][key] = count + 1


def _edition(state: dict, level: str) -> Edition:
    return Edition.objects.select_related("work", "source_edition").get(pk=state["editions"][level])


def _busy(edition: Edition) -> str:
    """The edition's own jobs still queued or running, named, or an empty string."""

    names = (
        edition.pipeline_runs.filter(status__in=ACTIVE, updated_at__gte=timezone.now() - STALL)
        .exclude(processor_version=VERSION)
        .values_list("stage", flat=True)
    )
    return ", ".join(sorted(set(names)))


def _stalled(job: PipelineRun | None) -> bool:
    return job is not None and job.updated_at < timezone.now() - STALL


# Steps. Each returns ("wait", why), ("goto", step, what happened), ("ready", note) or
# raises Held.


def _source(run: PipelineRun, state: dict, level: str) -> tuple:
    """The source needs its own level before a ladder can be read from it."""

    from almonium_book_processor.catalog.chapter_analysis import analysis_context, queue_analysis

    source = run.edition
    context = analysis_context(source)
    reading = context.get("projection_state")
    if reading == "complete":
        return ("goto", "probe", "The source's chapters have their levels.")
    if reading in ACTIVE and not _stalled(context.get("chapter_analysis_run")):
        return ("wait", "The source's chapters are being read.")
    _started(state, "source analysis")
    queue_analysis(str(source.id))
    return ("wait", "The source's chapters are being read.")


def _probe(run: PipelineRun, state: dict, level: str) -> tuple:
    from almonium_book_processor.catalog.adaptation_floor import ladder, queue_probe

    source = run.edition
    row = next((r for r in ladder(source) if r["level"] == level), None)
    if row is None:
        raise Held(f"{level} is not below this book's own level.")
    if row["state"] in ("reached", "generated"):
        edition = (
            source.work.editions.filter(
                edition_type=Edition.EditionType.ADAPTATION, source_edition=source
            )
            .exclude(literary_register=Edition.LiteraryRegister.LIGHTLY_MODERNISED)
            .order_by("-created_at")
        )
        from almonium_book_processor.catalog.adaptation_quality import adaptation_target

        found = next((e for e in edition if adaptation_target(e) == level), None)
        if found is None:
            raise Held(f"The {level} edition the ladder speaks of could not be found.")
        state["editions"][level] = str(found.id)
        return ("goto", "levels", f"A {level} edition exists already: {found.slug}.")
    if row["state"] == "probe_passed":
        return ("goto", "write", "The probe passed.")
    if row["state"] == "probing":
        return ("wait", "The probe is running.")
    if row["state"] == "probe_failed":
        raise Held(f"The {level} probe failed: {row['note']}")
    if not row["can_probe"]:
        raise Held(f"{level} cannot be probed: {row['note']}")
    _started(state, f"probe {level}")
    with transaction.atomic():
        queue_probe(source.id, level)
    return ("wait", "The probe is running.")


def _write(run: PipelineRun, state: dict, level: str) -> tuple:
    from almonium_book_processor.catalog.book_adaptation import queue_book

    books = state.setdefault("books", {})
    book = PipelineRun.objects.filter(pk=books.get(level)).first() if books.get(level) else None
    if book is None or book.status in (PipelineRun.Status.FAILED, PipelineRun.Status.CANCELLED):
        _started(state, f"book {level}")
        with transaction.atomic():
            book = queue_book(run.edition_id, target_level=level)
        books[level] = str(book.id)
        state["editions"][level] = str(book.edition_id)
    if book.status == PipelineRun.Status.SUCCEEDED:
        return ("goto", "levels", f"The {level} edition is written: {book.edition.slug}.")
    return ("wait", f"The {level} edition is being written ({book.progress}%).")


def _levels(run: PipelineRun, state: dict, level: str) -> tuple:
    """The judges' reading of the edition as it stands, once its other jobs are done."""

    from almonium_book_processor.catalog.chapter_analysis import analysis_context, queue_analysis

    edition = _edition(state, level)
    if busy := _busy(edition):
        return ("wait", f"The edition's own jobs are running: {busy}.")
    reading = analysis_context(edition).get("projection_state")
    if reading == "complete":
        return ("goto", "mend", "Every chapter has the judges' reading.")
    _started(state, f"levels {level} after {_changes(state, level)} changes", STARTS + 1)
    queue_analysis(str(edition.id))
    return ("wait", "The judges are reading the edition.")


def _changes(state: dict, level: str) -> int:
    """How often this level's text was changed here; a reading is counted per text."""

    mended = sum(len(steps) for steps in state["mended"].get(level, {}).values())
    return mended + state["settled"].get(level, 0)


def _mend(run: PipelineRun, state: dict, level: str) -> tuple:
    """A chapter read above the target: its cited paragraphs once, the whole chapter once."""

    from almonium_book_processor.catalog.adaptation_quality import adaptation_quality
    from almonium_book_processor.catalog.adaptation_wording import (
        check_chapter,
        revise_chapter,
        spot_fix_chapter,
    )

    edition = _edition(state, level)
    quality = adaptation_quality(edition)
    if not quality.get("adaptation_blocker"):
        split = quality.get("adaptation_split_chapters") or []
        note = "Every chapter holds the level."
        if split:
            note = (
                f"The level holds; the judges disagree about chapter(s) {_list(split)}, "
                "within the allowance."
            )
        return ("goto", "audit", note)
    above = quality.get("adaptation_above_chapters") or []
    if not above:
        raise Held(quality["adaptation_blocker"])
    mended = state["mended"].setdefault(level, {})
    for sequence in above:
        done = mended.setdefault(str(sequence), [])
        chapter = edition.chapters.get(sequence=sequence)
        if "paragraphs" not in done:
            done.append("paragraphs")
            spot = spot_fix_chapter(edition, chapter)
            if spot["changed"]:
                return (
                    "goto",
                    "levels",
                    f"Chapter {sequence}: {spot['changed']} cited paragraph(s) rewritten.",
                )
        if "chapter" not in done:
            done.append("chapter")
            outcome = revise_chapter(edition, chapter, check_chapter(edition, chapter))
            if outcome["applied"]:
                return ("goto", "levels", f"Chapter {sequence}: rewritten whole and applied.")
    raise Held(
        f"Chapter(s) {_list(above)} still read above {level} after the cited paragraphs and "
        "the whole chapter were each rewritten once."
    )


def _list(numbers: list) -> str:
    return ", ".join(str(number) for number in numbers)


def _audit(run: PipelineRun, state: dict, level: str) -> tuple:
    from almonium_book_processor.catalog.fidelity_audit import audit_context, queue_edition_audit

    edition = _edition(state, level)
    if busy := _busy(edition):
        return ("wait", f"The edition's own jobs are running: {busy}.")
    context = audit_context(edition)
    audit = context["fidelity_audit_state"]
    if audit == "current":
        return ("goto", "settle", "Both auditors have read the edition as it stands.")
    if audit in ACTIVE and not _stalled(context.get("fidelity_audit_run")):
        return ("wait", "The auditors are reading the edition.")
    _started(state, f"audit {level} after {_changes(state, level)} changes")
    queue_edition_audit(edition.id)
    return ("wait", "The auditors are reading the edition.")


def _settle(run: PipelineRun, state: dict, level: str) -> tuple:
    """Write in the corrections more than one model stands behind; the audit reads them next.

    The audit is not carried over its own words here. A correction can be right and still
    land wrong, and with nobody reading the book the auditors are the ones to notice: the
    chapters a correction touched are read again, and only those.
    """

    from almonium_book_processor.catalog.fidelity_audit import SEVERITIES, open_findings
    from almonium_book_processor.catalog.services import apply_fidelity_findings

    edition = _edition(state, level)
    rounds = state["settled"].get(level, 0)
    ready = [
        finding.id
        for finding in open_findings(edition)
        if finding.can_apply and finding.suggested_text and backed(finding.evidence)
    ]
    if not ready or rounds >= SETTLE_ROUNDS:
        left = f"; {len(ready)} agreed correction(s) left after {rounds} rounds" if ready else ""
        return ("goto", "verdict", f"No corrections left to apply{left}.")
    applied = apply_fidelity_findings(
        edition=edition, reviewer=None, severities=list(SEVERITIES), only=set(ready), carry=False
    )
    state["settled"][level] = rounds + 1
    return (
        "goto",
        "levels",
        f"{applied} correction(s) both models stand behind were written in; the changed "
        "chapters go back to the judges and the auditors.",
    )


def _verdict(run: PipelineRun, state: dict, level: str) -> tuple:
    from almonium_book_processor.catalog.adaptation_floor import edition_gates

    edition = _edition(state, level)
    gates = edition_gates(edition)
    if not gates["reached"]:
        reasons = [gates["difficulty_note"]]
        if not gates["fidelity_ok"]:
            reasons.append(
                f"Fidelity: the audit is {gates['fidelity_state']} with "
                f"{gates['fidelity_open_findings']} material finding(s) open that could not "
                "be corrected automatically."
            )
        raise Held(*reasons)
    note = "Both gates passed."
    if state["sign_off"]:
        _sign_off(edition, run)
        note = "Both gates passed; signed off without a person."
    if state["promote_to"]:
        return ("goto", "promote", note)
    return ("ready", note)


@transaction.atomic
def _sign_off(edition: Edition, run: PipelineRun) -> None:
    """Close the review as the gates stand. No person is recorded, because none read it."""

    from almonium_book_processor.catalog.services import complete_review

    edition = Edition.objects.select_for_update().get(pk=edition.id)
    open_items = edition.warnings.exclude(severity=QAWarning.Severity.INFO).filter(resolved_at=None)
    # the adaptation's own review items ask a person to look; here the gates answered
    other = sorted(
        set(open_items.exclude(code__startswith="adaptation_").values_list("code", flat=True))
    )
    if other:
        raise Held(f"Review items of another kind are open: {', '.join(other)}.")
    open_items.update(resolved_at=timezone.now(), resolved_by=None, updated_at=timezone.now())
    if edition.status == Edition.Status.REVIEW:
        complete_review(
            edition=edition,
            reviewer=None,
            notes=(
                f"Signed off by the automatic production {run.id}: the level gate and the "
                "fidelity gate both passed. No person reviewed this edition."
            ),
        )


def _promote(run: PipelineRun, state: dict, level: str) -> tuple:
    from almonium_book_processor import __version__
    from almonium_book_processor.catalog.promotion import promotion_blocker, promotion_target
    from almonium_book_processor.catalog.tasks import promote_edition

    edition = _edition(state, level)
    promotions = state.setdefault("promotions", {})
    if level not in promotions:
        target = promotion_target(state["promote_to"])
        if target is None:
            raise Held(f"No promotion target named {state['promote_to']!r} is configured here.")
        if blocked := promotion_blocker(edition):
            raise Held(blocked)
        publish = bool(state["publish"])
        promotion = PipelineRun.objects.create(
            edition=edition,
            stage=PipelineRun.Stage.PROMOTE,
            processor_version=__version__,
            input_hash="",
            idempotency_key=f"{edition.id}:promote:{target.name}:{uuid.uuid4().hex}",
            summary={"target": target.name, "target_url": target.base_url, "publish": publish},
        )
        promotions[level] = str(promotion.id)
        transaction.on_commit(lambda: promote_edition.delay(str(promotion.id), publish=publish))
        return ("wait", f"Promotion to {target.name} is queued.")
    promotion = PipelineRun.objects.get(pk=promotions[level])
    if promotion.status == PipelineRun.Status.SUCCEEDED:
        return ("ready", f"Both gates passed; promoted to {state['promote_to']}.")
    if promotion.status in (PipelineRun.Status.FAILED, PipelineRun.Status.CANCELLED):
        raise Held(f"Promotion to {state['promote_to']} failed: {promotion.error}")
    return ("wait", f"Promotion to {state['promote_to']} is running.")


STEPS = {
    "source": _source,
    "probe": _probe,
    "write": _write,
    "levels": _levels,
    "mend": _mend,
    "audit": _audit,
    "settle": _settle,
    "verdict": _verdict,
    "promote": _promote,
}


def production_context(edition: Edition) -> dict:
    """The latest production of a source edition, for its page."""

    run = edition.pipeline_runs.filter(processor_version=VERSION).order_by("-created_at").first()
    if run is None:
        return {"production": None}
    state = run.summary
    return {
        "production": {
            "run": run,
            "active": run.status in ACTIVE,
            "levels": state["levels"],
            "step": state["step"],
            "outcomes": state["outcomes"],
            "log": state["log"][-12:],
        }
    }
