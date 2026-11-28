"""The factory: books made without a person while the plan accounts have room.

Readers want books; Almonium ranks the wants and knows where each work's free text is. This
host owns the plan accounts the writers and judges run on, so the factory lives here: a timer
calls ``tick`` every quarter of an hour. A tick tells Almonium how every book under way is
getting on, and if fewer than ``FACTORY_MAX_PRODUCTIONS`` are under way and each plan has more
than ``FACTORY_RESERVE_PERCENT`` of its week left, it asks Almonium for the queue, reserves the
first wanted work that has a free text in a language the processor reads, and ingests that text.
When the text reaches the shelf (``tasks._finish_normalized_pipeline``) the production the ingest
carries is queued: the levels, where the book is wanted in its own language, or the translation,
and the finished editions are promoted and published to ``FACTORY_PROMOTE_TO``. Publication
settles the wants.

Two switches decide whether it does: ``FACTORY_ENABLED`` says this host is the one that makes
the books, and the dashboard's Start and Pause say whether it starts new ones now
(``FactorySwitch``; paused until first started). A paused factory still reports. Books already
under way are paused one at a time (``production.pause_book``); the dashboard's queue lists
them, the factory's and the ones started by hand, with a button each.

Everything Almonium is told goes through the signed internal surface the rights check uses.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from django.conf import settings
from django.db.models import Q
from django.utils import timezone

from almonium_book_processor.catalog.models import (
    Edition,
    FactorySwitch,
    PipelineRun,
    SourceDownload,
)
from almonium_book_processor.catalog.plan_meters import PlanMeter, plan_meters
from almonium_book_processor.catalog.promotion import (
    PromotionError,
    import_bundle,
    promotion_target,
    source_compatibility_problem,
)
from almonium_book_processor.catalog.promotion_client import PromotionClient
from almonium_book_processor.catalog.publication import PublicationError, _signed_post
from almonium_book_processor.languages import LANGUAGE_CODES

logger = logging.getLogger(__name__)

QUEUE_PATH = "/internal/books/factory/queue"
PREPARATIONS_PATH = "/internal/books/factory/preparations"
# the plans the books need: a production with no room on either is not started
PROVIDERS = ("codex", "claude-code")
# the production's statuses the book is still under way in
ACTIVE = (PipelineRun.Status.QUEUED, PipelineRun.Status.RUNNING)
# who started a production of a book a reader opened as it arrived (its summary's origin)
LIVE = "live"


def tick() -> dict[str, Any]:
    """One pass: report every book under way, then start one more if there is room."""

    if not settings.FACTORY_ENABLED:
        return {"started": None, "reason": "The factory is off (FACTORY_ENABLED)."}
    result = _tick()
    FactorySwitch.objects.update_or_create(
        pk=1, defaults={"ticked_at": timezone.now(), "tick_note": result["reason"][:300]}
    )
    return result


def _tick() -> dict[str, Any]:
    reported = report_preparations()
    busy = under_way() + live_under_way()
    if not switch().running:
        return _result(reported, busy, None, "The factory is paused; nothing new is started.")
    if len(busy) >= settings.FACTORY_MAX_PRODUCTIONS:
        return _result(reported, busy, None, f"{len(busy)} book(s) under way already.")
    if (room := plans_room()) is not None:
        return _result(reported, busy, None, room)
    try:
        # a reader is already reading it: its levels come before the next wanted book
        opened = start_live_levels()
    except (PromotionError, ValueError) as error:
        logger.warning("The factory could not take a book a reader opened: %s", error)
        opened = None
    if opened is not None:
        return _result(reported, busy, opened.slug, f"Started the levels of {opened.title!r}.")
    try:
        queue = _signed_post(QUEUE_PATH, {}, failure="The wanted queue could not be read")
    except PublicationError as error:
        return _result(reported, busy, None, str(error))
    for row in queue if isinstance(queue, list) else []:
        source = row.get("source")
        if not source or source.get("language") not in LANGUAGE_CODES:
            continue
        if already_fetched(source):
            # the text is on the shelf already, fetched for another want of the same work: a
            # second fetch made a second book (Candide and Marianela on 17 October 2026). Until
            # one book can serve several wants, the want waits rather than duplicating it.
            logger.info("The factory leaves %s: its text is on the shelf", row.get("title"))
            continue
        try:
            started = start(row, source)
        except (PublicationError, ValueError) as error:
            logger.warning("The factory could not start %s: %s", row.get("title"), error)
            continue
        return _result(reported, busy, started.slug, f"Started {row.get('title')!r}.")
    return _result(reported, busy, None, "Nothing in the queue has a free text to start from.")


def already_fetched(source: dict) -> bool:
    """Whether a book was already fetched from this source page, under any want."""

    return SourceDownload.objects.filter(source_page_url=source.get("pageUrl", "")).exists()


def _result(reported: int, busy: list, started: str | None, reason: str) -> dict[str, Any]:
    return {"reported": reported, "under_way": len(busy), "started": started, "reason": reason}


def switch() -> FactorySwitch:
    """The factory's switch as last pressed; an unsaved paused one before the first press."""

    return FactorySwitch.objects.filter(pk=1).first() or FactorySwitch(pk=1)


def set_running(running: bool, *, by: str = "") -> None:
    FactorySwitch.objects.update_or_create(
        pk=1, defaults={"running": running, "changed_by": by[:150]}
    )


def queue() -> list[dict[str, Any]]:
    """Every book under way, oldest first: the ingests that carry a production from their
    download, and every production however it was started. A book is a source edition."""

    from almonium_book_processor.catalog.production import VERSION, current_steps, paused_books

    paused = paused_books()
    rows: dict = {}
    for edition in under_way():
        if _production(edition) is None:
            rows[edition.id] = {
                "edition": edition,
                "since": edition.created_at,
                "step": _ingest_step(edition),
            }
    for run in PipelineRun.objects.filter(
        processor_version=VERSION, status__in=ACTIVE
    ).select_related("edition__work"):
        rows[run.edition_id] = {
            "edition": run.edition,
            "since": run.created_at,
            "step": (
                "waiting for a worker"
                if run.status == PipelineRun.Status.QUEUED
                else current_steps(run) or "finishing"
            ),
            "run": run,
        }
    for edition_id, row in rows.items():
        row["paused"] = edition_id in paused
    return sorted(rows.values(), key=lambda row: row["since"])


def _ingest_step(edition: Edition) -> str:
    if edition.source_download.status == SourceDownload.Status.PENDING:
        return "downloading"
    if edition.status in (Edition.Status.READY, Edition.Status.REVIEW):
        return "waiting for its production"
    return "ingesting"


def plans_room() -> str | None:
    """Why the plans leave no room for another book; ``None`` when they do.

    Each plan needs an open account with more than the reserve left; a paused account takes no
    calls, and a meter the host's timer has not refreshed for over an hour says nothing, so
    neither counts as room.
    """

    meters = [meter for meter in plan_meters() if not meter.stale and not meter.paused]
    for provider in PROVIDERS:
        own = [meter for meter in meters if meter.provider == provider]
        if not own:
            return f"No open {PlanMeter.label(provider)} account with a fresh meter reading."
        if all(100 - meter.week_percent <= settings.FACTORY_RESERVE_PERCENT for meter in own):
            return (
                f"Every {PlanMeter.label(provider)} account is within the reserve of "
                f"{settings.FACTORY_RESERVE_PERCENT}% of its week."
            )
    return None


def under_way() -> list[Edition]:
    """The factory's books between the download and the finished production."""

    editions = Edition.objects.filter(source_download__isnull=False).exclude(
        Q(status=Edition.Status.FAILED) | Q(source_download__status=SourceDownload.Status.FAILED)
    )
    return [edition for edition in editions.select_related("source_download") if not _done(edition)]


def live_under_way() -> list[Edition]:
    """The books readers opened as they arrived whose levels are being made here."""

    from almonium_book_processor.catalog.production import VERSION

    runs = PipelineRun.objects.filter(
        processor_version=VERSION, status__in=ACTIVE, summary__origin=LIVE
    ).select_related("edition")
    return [run.edition for run in runs]


def _done(edition: Edition) -> bool:
    """Whether the book this ingest started is finished, well or not."""

    if edition.source_download.status == SourceDownload.Status.PENDING:
        return False
    if edition.status not in (
        Edition.Status.READY,
        Edition.Status.REVIEW,
        Edition.Status.PUBLISHED,
    ):
        return False  # being ingested
    if not edition.source_download.production:
        return True  # an ingest that stops at the shelf
    production = _production(edition)
    return production is not None and production.status not in ACTIVE


def _production(edition: Edition) -> PipelineRun | None:
    from almonium_book_processor.catalog.production import VERSION

    return edition.pipeline_runs.filter(processor_version=VERSION).order_by("-created_at").first()


def start(row: dict, source: dict) -> Edition:
    """Reserve the wanted work with Almonium and ingest its free text, with what to make of it."""

    from almonium_book_processor.catalog.services import create_source_ingest
    from almonium_book_processor.catalog.source_download import check_download_url, check_page_url

    kind = str(source.get("kind", "")).lower()
    check_download_url(source["downloadUrl"], kind)
    check_page_url(source["pageUrl"], kind)
    wanted_in = str(row["language"]).lower()
    text_in = source["language"]
    levels = list(settings.FACTORY_LEVELS) if wanted_in == text_in else []
    languages = [] if wanted_in == text_in else [wanted_in]
    reserved = _signed_post(
        PREPARATIONS_PATH,
        {
            "catalogWorkId": row["catalogWorkId"],
            "language": row["language"],
            "sourceId": source["id"],
        },
        failure="The wanted work could not be reserved",
    )
    edition, _ = create_source_ingest(
        external_id=uuid.UUID(reserved["preparationId"]),
        download_url=source["downloadUrl"],
        source_kind=kind,
        source_page_url=source["pageUrl"],
        title=row["title"],
        author=row.get("author") or "",
        language=text_in,
        publication_year=row.get("publicationYear"),
        levels=levels,
        languages=languages,
    )
    report(edition)
    return edition


def start_live_levels() -> Edition | None:
    """Take one book a reader opened as it arrived, and make what it went to the shelf without.

    Such a book was fetched and published where the readers are (``SourceDownload.live``),
    with a stand-in level and no adaptations, because nothing there may spend the plans.
    Those environments are ``FACTORY_LIVE_FROM``, asked in order; an export listing marks the book
    ``awaiting_levels``. The same edition is
    pulled here, so the text and every reader's place in it stay what they are, and a
    production is queued like any other: the level is judged, the adaptations written, and
    all of it promoted back and published, which replaces the stand-in level.

    One book a tick, oldest listing order. A book already tried here is not tried again by
    itself, whatever came of it: a held production is a person's to look at.
    """

    for name in settings.FACTORY_LIVE_FROM:
        target = promotion_target(name)
        if target is None:
            logger.warning("No promotion target named %s to take opened books from", name)
            continue
        try:
            if (edition := _take_opened_book(target)) is not None:
                return edition
        except (PromotionError, ValueError) as error:
            # one environment that cannot be asked does not keep the next from being asked
            logger.warning("The factory could not take an opened book from %s: %s", name, error)
    return None


def _take_opened_book(target) -> Edition | None:
    from almonium_book_processor.catalog.production import VERSION, queue_production

    client = PromotionClient(target)
    listing = client.exports()
    if problem := source_compatibility_problem(listing):
        raise PromotionError(problem)
    for entry in listing.get("editions", []):
        if not entry.get("awaiting_levels") or entry.get("language") not in LANGUAGE_CODES:
            continue
        if PipelineRun.objects.filter(edition_id=entry["id"], processor_version=VERSION).exists():
            continue
        import_bundle(client.pull(entry["slug"]), origin=listing.get("origin"))
        edition = Edition.objects.get(id=entry["id"])
        queue_production(
            edition.id,
            list(settings.FACTORY_LEVELS),
            promote_to=target.name,
            publish=True,
            origin=LIVE,
        )
        return edition
    return None


def continue_production(edition: Edition) -> PipelineRun | None:
    """Queue the production a source ingest carries, now that its text is on the shelf."""

    from almonium_book_processor.catalog.production import queue_production

    download = SourceDownload.objects.filter(edition=edition).first()
    if download is None or not download.production:
        return None
    wanted = download.production
    try:
        return queue_production(
            edition.id,
            wanted.get("levels", []),
            languages=wanted.get("languages", []),
            promote_to=settings.FACTORY_PROMOTE_TO,
            publish=bool(settings.FACTORY_PROMOTE_TO),
        )
    except ValueError as error:
        logger.warning("No production for %s: %s", edition.slug, error)
        return None


def report_preparations() -> int:
    """Tell Almonium how every unfinished book, and every book just finished, is getting on."""

    reported = 0
    for edition in Edition.objects.filter(source_download__isnull=False).select_related(
        "source_download"
    ):
        download = edition.source_download
        if download.reported_final:
            continue
        try:
            report(edition)
            reported += 1
        except PublicationError as error:
            logger.warning("Almonium was not told about %s: %s", edition.slug, error)
    return reported


def report(edition: Edition) -> dict[str, Any]:
    """The ingest status Almonium polls for, pushed, with the production's word on top."""

    status = preparation_status(edition)
    _signed_post(
        f"{PREPARATIONS_PATH}/{edition.source_download.external_id}/status",
        status,
        failure="The preparation's status could not be reported",
    )
    if status["phase"] in ("published", "failed", "ready") and _done(edition):
        SourceDownload.objects.filter(pk=edition.source_download.pk).update(reported_final=True)
    return status


def preparation_status(edition: Edition) -> dict[str, Any]:
    from almonium_book_processor.catalog.translation_jobs import library_ingest_status

    status = library_ingest_status(edition)
    status["published_at"] = status["published_at"].isoformat() if status["published_at"] else None
    status["published_book_id"] = (
        str(status["published_book_id"]) if status["published_book_id"] else None
    )
    production = _production(edition) if edition.source_download.production else None
    if production is None:
        return status
    if production.status in ACTIVE:
        status["phase"] = "producing"
    elif production.status == PipelineRun.Status.SUCCEEDED:
        status["phase"] = "published" if settings.FACTORY_PROMOTE_TO else "ready"
    else:
        status["phase"] = "failed"
        status["error"] = production.error or status["error"]
    return status
