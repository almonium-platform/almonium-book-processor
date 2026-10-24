"""A book's adaptations and translations made from start to verdict with nobody reading them.

One production takes a source edition and the levels asked for, highest first, and carries
each through the steps a person used to start by hand: the source's levels, the probe, the
book, the judges' reading, the mending of chapters read above the target, the fidelity audit,
the corrections both auditors stand behind, the audit again on what those changed, and a
verdict. A level that passes both gates is signed off and, if asked, promoted; a level that
does not is held with the reasons, and the levels below it are not attempted.

The languages asked for do not depend on the levels and are made beside them, on a track of
their own that moves on every tick the levels' track does: each is translated, read by the
two editors, corrected where both stand behind a correction, and signed off unless a serious
finding they agree on could not be corrected.

Nothing here decides quality. Each step asks the same gate a person's click would have met,
and the production only knows what to start next, how long to wait, and when to stop trying:
a failed step is started once more, a chapter is mended once by paragraph and once whole,
corrections are applied and re-read twice at most, and a step nobody finishes in three hours
holds the book instead of waiting for ever.

Before any of it, Almonium is asked whether the work may be prepared at all: editions are
made in Ukraine and hosted in Germany, and a work under copyright in either holds every
target before anything is spent. An unknown verdict, or a check that could not be made, goes
ahead with the reason logged; Almonium checks the publication itself again.

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

from almonium_book_processor.ai.cli_calls import ALLOWANCE_USED_UP
from almonium_book_processor.catalog.fidelity_audit import backed
from almonium_book_processor.catalog.models import (
    Edition,
    PipelineRun,
    QAWarning,
    RemovalReason,
)

VERSION = "production-v1"
TICK_SECONDS = 30
# A whole book is written in about half an hour and audited in a quarter.
STEP_TIMEOUT = timedelta(hours=3)
# How often one thing is started before the book is held: the first time and once more.
STARTS = 2
# How often corrections are applied and the changed chapters audited again. Each round
# costs a re-read of the chapters the corrections touched, and the auditors usually find
# something new there: The Sign of Four's B1 was held with two agreed, placeable corrections
# left after two rounds. A round that applies nothing ends it earlier.
SETTLE_ROUNDS = 5
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


def queue_production(
    source_id,
    levels: list[str],
    *,
    languages: list[str] | None = None,
    register: str = "",
    sign_off: bool = True,
    promote_to: str = "",
    publish: bool = False,
) -> PipelineRun:
    """Start a production from a source edition, or return the one under way.

    ``levels`` are the adaptations to make and ``languages`` the translations, in the
    ``register`` named or the first one the catalogue knows.
    """

    from almonium_book_processor.catalog.adaptation_floor import PROBE_LEVELS
    from almonium_book_processor.catalog.chapter_projections import LEVELS
    from almonium_book_processor.catalog.tasks import produce_edition

    if any(level not in PROBE_LEVELS for level in levels):
        raise ValueError(f"Choose the levels to produce from {', '.join(PROBE_LEVELS)}.")
    levels = sorted(dict.fromkeys(levels), key=LEVELS.index, reverse=True)
    languages = list(
        dict.fromkeys(code.strip().lower() for code in languages or [] if code.strip())
    )
    if not levels and not languages:
        raise ValueError("Name at least one level or one language to produce.")
    register = register or Edition.LiteraryRegister.values[0]
    if register not in Edition.LiteraryRegister.values:
        raise ValueError(f"Unknown register: {register}")
    with transaction.atomic():
        source = Edition.objects.select_for_update().select_related("work").get(pk=source_id)
        if source.edition_type == Edition.EditionType.ADAPTATION:
            raise ValueError("Produce from the original edition, not from an adaptation.")
        if source.language in languages:
            raise ValueError("A translation is into another language than the source's.")
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
                "languages": languages,
                "register": register,
                "tracks": _fresh_tracks(levels, languages),
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


# What holds a book without saying anything about the book: a step that broke too often, a
# plan whose allowance ran out, a worker that died under it. These are started again.
CIRCUMSTANTIAL_HOLDS = ("was started", ALLOWANCE_USED_UP, "Left behind")


def requeue_held(*, allowance_only: bool = False, older_than: timedelta = timedelta(minutes=30)):
    """Start again the productions that were held by circumstance, not by the book.

    A hold names its cause in the run's error. With ``allowance_only`` only the ones a plan's
    used-up allowance held are started, which the meter's timer does once an account answers
    again; ``older_than`` keeps a book from being started twice in one bad hour. The sources
    whose newest production is finished well or under way are left alone. Returns the runs.
    """

    causes = (ALLOWANCE_USED_UP,) if allowance_only else CIRCUMSTANTIAL_HOLDS
    cutoff = timezone.now() - older_than
    started = []
    newest_by_source: dict = {}
    for run in PipelineRun.objects.filter(processor_version=VERSION).order_by("-created_at"):
        newest_by_source.setdefault(run.edition_id, run)
    for run in newest_by_source.values():
        if run.status != PipelineRun.Status.FAILED or run.finished_at is None:
            continue
        if run.finished_at > cutoff or not any(cause in (run.error or "") for cause in causes):
            continue
        state = run.summary
        started.append(
            queue_production(
                run.edition_id,
                state.get("levels", []),
                languages=state.get("languages", []),
                register=state.get("register", ""),
                sign_off=state.get("sign_off", True),
                promote_to=state.get("promote_to", ""),
                publish=state.get("publish", False),
            )
        )
    return started


def _fresh_tracks(levels: list[str], languages: list[str]) -> dict:
    """The two cursors a production walks: the levels down the ladder, and the languages."""

    now = timezone.now().isoformat()
    tracks = {}
    if levels:
        tracks["levels"] = {"targets": levels, "index": 0, "step": "source", "since": now}
    if languages:
        tracks["languages"] = {"targets": languages, "index": 0, "step": "translate", "since": now}
    return tracks


def _tracks(state: dict) -> dict:
    """The production's cursors; a run started with one cursor over both lists gets two."""

    if "tracks" not in state:
        tracks = _fresh_tracks(state["levels"], state.get("languages", []))
        done = state.get("index", 0)
        for name, track in tracks.items():
            offset = 0 if name == "levels" else len(state["levels"])
            track["index"] = min(max(0, done - offset), len(track["targets"]))
            if track["index"] < len(track["targets"]) and done >= offset:
                track["step"] = state.get("step", track["step"])
                track["since"] = state.get("since", track["since"])
        state["tracks"] = tracks
    return state["tracks"]


def advance(run_id) -> bool:
    """Move a production as far as it can go without waiting; say whether it is finished."""

    # a track that only waited is not asked again in the same call: its step would start
    # the same job once more, and count the start against the book
    moved = None
    for _ in range(2 * len(STEPS)):
        finished, moved = _advance_once(run_id, moved)
        if finished or not moved:
            return finished
    return False


def _advance_once(run_id, only: set[str] | None = None) -> tuple[bool, set[str]]:
    """One step of each track (of the tracks named in ``only``, when given).

    Whether the production is finished, and the tracks that moved to another step.
    """

    run = PipelineRun.objects.select_related("edition__work").get(pk=run_id)
    if run.processor_version != VERSION:
        raise ValueError("Not a production run.")
    if run.status in FINISHED:
        return True, False
    state = run.summary
    if run.status == PipelineRun.Status.QUEUED:
        run.status = PipelineRun.Status.RUNNING
        run.started_at = timezone.now()
        _read_meters(state, "started")
    if "rights" not in state and not _may_be_prepared(run, state):
        _finish(run, state)
        run.summary = state
        run.save()
        return True, set()
    moved = set()
    for name, track in _tracks(state).items():
        if track["index"] >= len(track["targets"]) or (only is not None and name not in only):
            continue
        target = track["targets"][track["index"]]
        step = track["step"]
        try:
            _refused(run, state, target)
            move = STEPS[step](run, state, target)
            if move[0] == "wait" and timezone.now() - parse_datetime(track["since"]) > STEP_TIMEOUT:
                raise Held(f"Nothing finished '{step}' in {STEP_TIMEOUT}: {move[1]}")
        except Held as held:
            move = ("hold", held.reasons)
        except Exception as error:
            # a step that breaks is started again on the next call, as often as its own
            # counters allow; one that keeps breaking holds the book with what it said
            try:
                _started(state, f"error:{target}:{step}", STARTS + 1)
                move = ("wait", f"{type(error).__name__}: {str(error)[:300]}; trying again")
            except Held:
                move = ("hold", [f"'{step}' failed: {type(error).__name__}: {str(error)[:300]}"])
        _apply(state, track, target, step, move)
        if move[0] != "wait":
            moved.add(name)
    finished = all(track["index"] >= len(track["targets"]) for track in _tracks(state).values())
    if finished:
        _finish(run, state)
    run.summary = state
    run.save()
    return finished, moved


def _apply(state: dict, track: dict, target: str, step: str, move: tuple) -> None:
    """Move one track's cursor by what its step said."""

    kind = move[0]
    if kind == "wait":
        _log(state, target, step, move[1], repeat=False)
        return
    if kind == "goto":
        _log(state, target, step, move[2])
        track["step"] = move[1]
        track["since"] = timezone.now().isoformat()
        return
    if kind == "ready":
        state["outcomes"][target] = {"outcome": "ready", "note": move[1]}
        _log(state, target, step, f"READY: {move[1]}")
        following = track["index"] + 1
    elif kind == "skip":
        state["outcomes"][target] = {"outcome": "not needed", "note": move[1]}
        _log(state, target, step, f"NOT NEEDED: {move[1]}")
        following = track["index"] + 1
    elif kind == "dropped":
        # a verdict, not a failure: the book does not come down to this level, and the levels
        # below it are further still
        state["outcomes"][target] = {"outcome": "not reached", "reasons": [move[1]]}
        _log(state, target, step, f"NOT REACHED: {move[1]}")
        following = track["index"] + 1
        if target in state["levels"]:
            for below in track["targets"][track["index"] + 1 :]:
                state["outcomes"][below] = {
                    "outcome": "not reached",
                    "reasons": [f"{target}, the level above, was not reached."],
                }
            following = len(track["targets"])
    else:
        reasons = move[1]
        state["outcomes"][target] = {"outcome": "held", "reasons": reasons}
        _log(state, target, step, "HELD: " + "; ".join(reasons))
        following = track["index"] + 1
        if target in state["levels"]:
            # the ladder is descended a rung at a time; the translations do not hang on it
            for skipped in track["targets"][track["index"] + 1 :]:
                state["outcomes"][skipped] = {
                    "outcome": "not attempted",
                    "reasons": [f"{target}, the level above, was held."],
                }
            following = len(track["targets"])
    track["index"] = following
    if following < len(track["targets"]):
        track["step"] = _first_step(state, track["targets"][following])
        track["since"] = timezone.now().isoformat()


def _finish(run: PipelineRun, state: dict) -> None:
    unfinished = [
        f"{target} {outcome['outcome']}: {' '.join(outcome.get('reasons', []))}"
        for target, outcome in state["outcomes"].items()
        if outcome["outcome"] not in ("ready", "not needed", "not reached")
    ]
    # a held book is a verdict, and it is shown where a failed job is: it needs a person
    run.status = PipelineRun.Status.FAILED if unfinished else PipelineRun.Status.SUCCEEDED
    run.error = "; ".join(unfinished)
    run.progress = 100
    run.finished_at = timezone.now()
    _read_meters(state, "finished")


def _read_meters(state: dict, label: str) -> None:
    """Keep both plans' meters with the production, where plans are what it runs on.

    A plan's price per list-price dollar is measured from meter readings around work of known
    list cost (``ai/pricing.py``). The Claude meter is the account's: the readings measure
    this production only if no other Claude Code session worked meanwhile.
    """

    from django.conf import settings

    if not settings.CELERY_TASK_ROUTES:
        return
    from almonium_book_processor.ai.claude_code_provider import claude_config_dir, claude_meter
    from almonium_book_processor.ai.codex_provider import codex_home, codex_meter

    codex_accounts = {}
    for home in settings.CODEX_HOMES or [None]:
        codex = codex_meter(home=home)
        codex_accounts[codex_home(home).name] = codex["used_percent"] if codex else None
    claude_accounts = {
        claude_config_dir(config_dir).name: claude_meter(config_dir=config_dir)
        for config_dir in settings.CLAUDE_CONFIG_DIRS or [None]
    }
    state.setdefault("meters", []).append(
        {
            "at": timezone.now().isoformat(),
            "label": label,
            # the first account of each plan, as the readings made with one account have it
            "codex_week_percent": next(iter(codex_accounts.values())),
            "claude": next(iter(claude_accounts.values())),
            "codex_accounts": codex_accounts,
            "claude_accounts": claude_accounts,
        }
    )


def _may_be_prepared(run: PipelineRun, state: dict) -> bool:
    """Ask Almonium once, before either track spends; a protected work holds every target."""

    first = _targets(state)[0]
    move = _rights(run, state, first)
    if move[0] == "goto":
        _log(state, first, "rights", move[2])
        return True
    state["outcomes"][first] = {"outcome": "held", "reasons": move[1]}
    _log(state, first, "rights", "HELD: " + "; ".join(move[1]))
    for track in _tracks(state).values():
        for target in track["targets"]:
            if target != first:
                state["outcomes"][target] = {
                    "outcome": "not attempted",
                    "reasons": [f"{first} was held: the book is not prepared."],
                }
        track["index"] = len(track["targets"])
    return False


def _first_step(state: dict, target: str) -> str:
    return "probe" if target in state["levels"] else "translate"


def _targets(state: dict) -> list[str]:
    """What a production makes, in order: the levels down the ladder, then the languages."""

    return [*state["levels"], *state.get("languages", [])]


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
        # the last note logged for this step is the reason it did not finish, when there is one:
        # "No chapter fits the pilot limits" held two Portuguese books as "did not finish".
        step = key.split()[0]
        reason = next(
            (
                entry["note"]
                for entry in reversed(state["log"])
                if entry["step"] == step and "trying again" in entry["note"]
            ),
            None,
        )
        suffix = f" Last: {reason.removesuffix('; trying again')}" if reason else ""
        raise Held(f"'{key}' was started {count} times and did not finish.{suffix}")
    state["starts"][key] = count + 1


def _refused(run: PipelineRun, state: dict, target: str) -> None:
    """Hold the target when a job this production started was refused for a used-up allowance.

    Every call on that plan fails the same way until its week turns, so starting the job
    again would only use up a start: on 24 October 2026 thirty-nine books did that against
    two empty Codex meters. The book waits instead, and no start is counted; the owner starts
    it again after the reset, and the finished reads are reused.
    """

    editions = [run.edition_id]
    if level_edition := state.get("editions", {}).get(target):
        editions.append(level_edition)
    refused = (
        PipelineRun.objects.filter(
            edition_id__in=editions,
            status=PipelineRun.Status.FAILED,
            created_at__gte=run.created_at,
            error__contains=ALLOWANCE_USED_UP,
        )
        .exclude(processor_version=VERSION)
        .order_by("-created_at")
        .first()
    )
    if refused is None:
        return
    said = refused.error[refused.error.index(ALLOWANCE_USED_UP) :].split(" — ")[0][:220]
    raise Held(
        f"The plan's allowance is used up, said the '{refused.stage}' job: {said} "
        "Start the book again after the reset."
    )


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


def _written(source: Edition, level: str) -> Edition | None:
    """The newest adaptation of ``source`` at ``level`` whose text stands, or None.

    A write that finished leaves the edition in review, ready or published; one that is still
    going, or that failed, has no text worth adopting.
    """

    from almonium_book_processor.catalog.adaptation_quality import adaptation_target

    standing = (
        source.work.editions.filter(
            edition_type=Edition.EditionType.ADAPTATION,
            source_edition=source,
            withdrawal_requested_at__isnull=True,
            status__in=(Edition.Status.REVIEW, Edition.Status.READY, Edition.Status.PUBLISHED),
        )
        .exclude(literary_register=Edition.LiteraryRegister.LIGHTLY_MODERNISED)
        .order_by("-created_at")
    )
    return next((e for e in standing if adaptation_target(e) == level and e.blocks.exists()), None)


def _stalled(job: PipelineRun | None) -> bool:
    return job is not None and job.updated_at < timezone.now() - STALL


# Steps. Each returns ("wait", why), ("goto", step, what happened), ("ready", note),
# ("skip", why the target is not needed) or raises Held. The rights check comes before
# them all, once for the production, and answers ("stop", reasons) to hold every target.


def _rights(run: PipelineRun, state: dict, level: str) -> tuple:
    """Ask Almonium whether the work may be prepared, before anything is spent on it.

    Editions are made in Ukraine and hosted in Germany, so a work under copyright in
    either is not prepared at all. An unknown verdict, usually a missing death year, goes
    ahead with its explanation logged; so does a check that could not be made, since
    Almonium checks the publication itself again and refuses a protected work there.
    """

    from almonium_book_processor.catalog.publication import RIGHTS_UNCHECKED, check_rights

    verdict = check_rights(run.edition)
    state["rights"] = {**verdict.as_dict(), "at": timezone.now().isoformat()}
    explanation = verdict.explanation or "no explanation given"
    if verdict.status == "PROTECTED":
        return ("stop", [f"Not prepared: {explanation}"])
    if verdict.status == RIGHTS_UNCHECKED:
        note = f"Rights not checked, going ahead (publication is checked again): {explanation}"
    elif verdict.status == "UNKNOWN":
        note = f"Rights unknown, going ahead: {explanation}"
    else:
        note = f"Rights: free in {', '.join(verdict.countries) or 'UA, DE'}. {explanation}"
    return ("goto", "source", note)


def _source(run: PipelineRun, state: dict, level: str) -> tuple:
    """The source needs its own level before a ladder can be read from it."""

    from almonium_book_processor.catalog.chapter_analysis import analysis_context, queue_analysis

    source = run.edition
    context = analysis_context(source)
    reading = context.get("projection_state")
    if reading == "complete":
        return ("goto", _first_step(state, level), "The source's chapters have their levels.")
    # the reading shows as partly done while the judges work; what says they are working is
    # the run itself
    analysis = context.get("chapter_analysis_run")
    if analysis is not None and analysis.status in ACTIVE and not _stalled(analysis):
        return ("wait", "The source's chapters are being read.")
    _started(state, "source analysis")
    queue_analysis(str(source.id))
    return ("wait", "The source's chapters are being read.")


def _probe(run: PipelineRun, state: dict, level: str) -> tuple:
    from almonium_book_processor.catalog.adaptation_floor import ladder, queue_probe

    source = run.edition
    row = next((r for r in ladder(source) if r["level"] == level), None)
    if row is None:
        # the ladder starts below the book's own level: nothing to make, and no rung is missed
        return ("skip", f"The book itself reads at {level} or below it.")
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
    if row["state"] not in ("not_reached", "probe_failed") and (written := _written(source, level)):
        # a book is written once: a production killed before its verdict leaves the edition
        # standing, and the next one judges that edition instead of paying for another
        state["editions"][level] = str(written.id)
        return ("goto", "levels", f"A {level} edition is written already: {written.slug}.")
    if row["state"] == "probe_passed":
        return ("goto", "write", "The probe passed.")
    if row["state"] == "probing":
        return ("wait", "The probe is running.")
    if row["state"] == "not_reached":
        return ("dropped", f"{level} was tried before and not reached: {row['note']}")
    if row["state"] == "probe_failed":
        return ("dropped", f"The {level} probe failed: {row['note']}")
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
    if book is None and (written := _written(run.edition, level)):
        state["editions"][level] = str(written.id)
        return ("goto", "levels", f"A {level} edition is written already: {written.slug}.")
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
    above = quality.get("adaptation_above_chapters") or []
    if not above:
        if quality.get("adaptation_blocker"):
            raise Held(quality["adaptation_blocker"])
        split = quality.get("adaptation_split_chapters") or []
        note = "Every chapter holds the level."
        if split:
            note = (
                f"The level holds; the judges disagree about chapter(s) {_list(split)}, "
                "within the allowance."
            )
        return ("goto", "audit", note)
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
    # the adapter has had both its tries at every chapter above the target
    tolerated = quality.get("adaptation_tolerated_chapters") or []
    if sorted(tolerated) == sorted(above):
        return (
            "goto",
            "audit",
            f"Chapter(s) {_list(above)} read one level above {level} after the cited "
            "paragraphs and the whole chapter were each rewritten once; within the "
            "allowance, each is shown to the reader at its own level.",
        )
    return _drop(
        run,
        state,
        level,
        edition,
        f"Chapter(s) {_list(above)} still read above {level} after the cited paragraphs and "
        "the whole chapter were each rewritten once.",
    )


def _drop(run: PipelineRun, state: dict, level: str, edition: Edition, reason: str) -> tuple:
    """The book does not come down to ``level``: its edition goes, and the ladder remembers.

    Holding it would ask a person to read what the adapter could not bring down, and nobody
    reads the books at the scale they are made. The record on the source keeps the level
    from being tried again; a person who disagrees purges the record and starts the book.
    """

    from almonium_book_processor.catalog.adaptation_floor import (
        record_unreached,
        refresh_adaptation_floor,
    )
    from almonium_book_processor.catalog.purge import purge_edition

    record_unreached(run.edition, level, reason, production=run)
    purge_edition(
        edition,
        reason=RemovalReason.OTHER,
        notes=f"The production {run.id} dropped {level}: {reason}",
    )
    state["editions"].pop(level, None)
    refresh_adaptation_floor(run.edition.work)
    return ("dropped", reason)


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

    A serious finding both auditors stand behind that names no replacement, or whose words
    cannot be found as one piece, is given to the adapter to rewrite the paragraph for its
    meaning, once per paragraph; the audit reads that again too.
    """

    from almonium_book_processor.catalog.adaptation_wording import repair_chapter
    from almonium_book_processor.catalog.fidelity_audit import SEVERITIES, open_findings
    from almonium_book_processor.catalog.services import apply_fidelity_findings

    edition = _edition(state, level)
    rounds = state["settled"].get(level, 0)
    findings = list(open_findings(edition))
    ready = [
        finding.id
        for finding in findings
        if finding.can_apply and finding.suggested_text and backed(finding.evidence)
    ]
    if rounds >= SETTLE_ROUNDS:
        left = f"; {len(ready)} agreed correction(s) left" if ready else ""
        return ("goto", "verdict", f"The {rounds} rounds of corrections are used up{left}.")
    if ready:
        applied = apply_fidelity_findings(
            edition=edition,
            reviewer=None,
            severities=list(SEVERITIES),
            only=set(ready),
            carry=False,
        )
        state["settled"][level] = rounds + 1
        return (
            "goto",
            "levels",
            f"{applied} correction(s) both models stand behind were written in; the changed "
            "chapters go back to the judges and the auditors.",
        )
    repaired = state.setdefault("repaired", {}).setdefault(level, [])
    stuck = [
        finding
        for finding in findings
        if finding.code == "fidelity_material"
        and backed(finding.evidence)
        and finding.stable_block_id not in repaired
    ]
    if not stuck:
        return ("goto", "verdict", "No corrections left to apply.")
    by_chapter: dict = {}
    for finding in stuck:
        by_chapter.setdefault(finding.block.chapter_id, []).append(finding)
    changed = 0
    for chapter_id, chapter_findings in by_chapter.items():
        chapter = edition.chapters.get(pk=chapter_id)
        outcome = repair_chapter(edition, chapter, chapter_findings)
        changed += outcome["changed"]
        repaired.extend(sorted({f.stable_block_id for f in chapter_findings}))
    if not changed:
        return (
            "goto",
            "verdict",
            "The adapter could not rewrite the paragraphs the findings name.",
        )
    state["settled"][level] = rounds + 1
    return (
        "goto",
        "levels",
        f"{changed} paragraph(s) rewritten for their meaning, as both auditors asked; they go "
        "back to the judges and the auditors.",
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
    # the edition's own review items ask a person to look; here the gates answered
    other = sorted(
        set(
            open_items.exclude(code__startswith="adaptation_")
            .exclude(code__startswith="translation_")
            .values_list("code", flat=True)
        )
    )
    if other:
        raise Held(f"Review items of another kind are open: {', '.join(other)}.")
    open_items.update(resolved_at=timezone.now(), resolved_by=None, updated_at=timezone.now())
    if edition.status == Edition.Status.REVIEW:
        complete_review(
            edition=edition,
            reviewer=None,
            notes=(
                f"Signed off by the automatic production {run.id}: every check it runs "
                "passed. No person reviewed this edition."
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


def _translate(run: PipelineRun, state: dict, language: str) -> tuple:
    """A parallel translation into ``language``: the one that exists, or a new one."""

    from django.conf import settings

    from almonium_book_processor.catalog.ai_translation import create_parallel_translation
    from almonium_book_processor.catalog.tasks import translate_edition_on_plan

    source = run.edition
    if language not in state["editions"]:
        existing = (
            source.work.editions.filter(
                source_edition=source,
                language=language,
                edition_type=Edition.EditionType.MACHINE_TRANSLATION,
                literary_register=state["register"],
            )
            .order_by("-created_at")
            .first()
        )
        if existing is not None and existing.blocks.exists():
            state["editions"][language] = str(existing.id)
            return ("goto", "review", f"A translation exists already: {existing.slug}.")
        edition = existing or create_parallel_translation(
            source_edition=source,
            target_language=language,
            register=state["register"],
            tier=settings.PRODUCTION_TRANSLATION_TIER,
        )
        state["editions"][language] = str(edition.id)
    edition = _edition(state, language)
    if edition.blocks.exists() and edition.status in (
        Edition.Status.REVIEW,
        Edition.Status.READY,
        Edition.Status.PUBLISHED,
    ):
        return ("goto", "review", f"The translation is written: {edition.slug}.")
    writing = edition.ai_runs.order_by("-created_at").first()
    fresh = writing is not None and writing.updated_at > timezone.now() - STALL
    if writing is not None and writing.status in ("queued", "submitted") and fresh:
        return ("wait", "The translation is being written.")
    _started(state, f"translation {language}")
    tier = settings.PRODUCTION_TRANSLATION_TIER
    transaction.on_commit(lambda: translate_edition_on_plan.delay(str(edition.id), tier))
    return ("wait", "The translation is being written.")


def _review(run: PipelineRun, state: dict, language: str) -> tuple:
    """The two editors' reading of the translation as it stands."""

    from almonium_book_processor.catalog.tasks import review_edition_translation
    from almonium_book_processor.catalog.translation_review import REVIEW_VERSION, review_plan

    edition = _edition(state, language)
    if busy := _busy(edition):
        return ("wait", f"The edition's own jobs are running: {busy}.")
    review = (
        edition.pipeline_runs.filter(
            processor_version=REVIEW_VERSION, input_hash=review_plan(edition)["hash"]
        )
        .order_by("-created_at")
        .first()
    )
    if review is not None and review.status == PipelineRun.Status.SUCCEEDED:
        return ("goto", "corrections", "Both editors have read the translation.")
    if review is not None and review.status in ACTIVE and not _stalled(review):
        return ("wait", "The editors are reading the translation.")
    _started(state, f"review {language}")
    transaction.on_commit(lambda: review_edition_translation.delay(str(edition.id)))
    return ("wait", "The editors are reading the translation.")


def _corrections(run: PipelineRun, state: dict, language: str) -> tuple:
    """Write in what both editors stand behind, then say whether anything serious is left.

    The editors report only serious findings, so what is left open and backed by both is a
    defect nobody could correct by replacing its span: that holds the translation. A finding
    one editor raised and the other refused is left for a person and holds nothing.
    """

    from almonium_book_processor.catalog.fidelity_audit import SEVERITIES, open_findings
    from almonium_book_processor.catalog.services import apply_fidelity_findings

    edition = _edition(state, language)
    if not state["settled"].get(language):
        state["settled"][language] = 1
        ready = [
            finding.id
            for finding in open_findings(edition)
            if finding.can_apply and finding.suggested_text and backed(finding.evidence)
        ]
        if ready:
            applied = apply_fidelity_findings(
                edition=edition,
                reviewer=None,
                severities=list(SEVERITIES),
                only=set(ready),
                carry=False,
            )
            return ("goto", "corrections", f"{applied} agreed correction(s) were written in.")
    left = [
        finding
        for finding in open_findings(edition)
        if finding.code == "fidelity_material" and backed(finding.evidence)
    ]
    if left:
        raise Held(
            f"{len(left)} serious finding(s) both editors stand behind could not be corrected "
            "by replacing the words they quote."
        )
    note = "Nothing serious that both editors stand behind is left."
    if state["sign_off"]:
        _sign_off(edition, run)
        note += " Signed off without a person."
    if state["promote_to"]:
        return ("goto", "promote", note)
    return ("ready", note)


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
    "translate": _translate,
    "review": _review,
    "corrections": _corrections,
}


RIGHTS_LABELS = {
    "FREE": "free",
    "PROTECTED": "under copyright",
    "UNKNOWN": "unknown",
    "UNCHECKED": "not checked",
}


def production_step(run: PipelineRun, edition_id) -> str:
    """What a production is doing about the edition it named, in a few words."""

    state = run.summary
    level = next(
        (k for k, v in (state.get("editions") or {}).items() if v == str(edition_id)), None
    )
    if run.status == PipelineRun.Status.QUEUED:
        return "waiting for a worker"
    for track in _tracks(state).values():
        if level in track["targets"]:
            if track["index"] >= len(track["targets"]):
                return "finishing"
            current = track["targets"][track["index"]]
            if current == level:
                return f"{track['step']} ({level})"
            return f"behind {current}"
    return "under way"


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
            "levels": _targets(state),
            "step": ", ".join(
                f"{track['step']} ({track['targets'][track['index']]})"
                for track in _tracks(state).values()
                if track["index"] < len(track["targets"])
            ),
            "outcomes": state["outcomes"],
            "rights": state.get("rights"),
            "rights_label": RIGHTS_LABELS.get((state.get("rights") or {}).get("status"), ""),
            "log": state["log"][-12:],
        }
    }
