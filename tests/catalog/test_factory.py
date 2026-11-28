"""The factory starts the next wanted book while the plans have room, and tells Almonium."""

from __future__ import annotations

import uuid
from datetime import timedelta

import pytest
from django.utils import timezone

from almonium_book_processor.catalog import factory
from almonium_book_processor.catalog.models import (
    Edition,
    PipelineRun,
    PlanMeterReading,
    SourceDownload,
    Work,
)
from almonium_book_processor.catalog.production import VERSION as PRODUCTION_VERSION
from almonium_book_processor.catalog.publication import PublicationError

pytestmark = pytest.mark.django_db

WORK_ID = str(uuid.uuid4())
SOURCE = {
    "id": str(uuid.uuid4()),
    "kind": "GUTENBERG",
    "language": "en",
    "pageUrl": "https://www.gutenberg.org/ebooks/345",
    "downloadUrl": "https://www.gutenberg.org/ebooks/345.epub3.images",
}
ROW = {
    "catalogWorkId": WORK_ID,
    "language": "UK",
    "title": "Dracula",
    "author": "Bram Stoker",
    "publicationYear": 1897,
    "source": SOURCE,
}


class Almonium:
    """What the product API answers the factory, and what it was told."""

    def __init__(self, queue):
        self.queue = queue
        self.posts = []
        self.preparation_id = uuid.uuid4()

    def __call__(self, path, payload, *, failure):
        self.posts.append((path, payload))
        if path == factory.QUEUE_PATH:
            return self.queue
        if path == factory.PREPARATIONS_PATH:
            return {"preparationId": str(self.preparation_id)}
        return {}

    def reports(self):
        return [payload for path, payload in self.posts if path.endswith("/status")]


@pytest.fixture
def almonium(monkeypatch, settings):
    settings.FACTORY_ENABLED = True
    factory.set_running(True)
    settings.FACTORY_MAX_PRODUCTIONS = 2
    settings.FACTORY_RESERVE_PERCENT = 15
    settings.FACTORY_LEVELS = ["B2", "B1"]
    settings.FACTORY_PROMOTE_TO = "staging"
    answers = Almonium([ROW])
    monkeypatch.setattr(factory, "_signed_post", answers)
    monkeypatch.setattr(
        "almonium_book_processor.catalog.tasks.download_source_edition.delay",
        lambda edition_id: None,
    )
    return answers


def meters(codex=30, claude=40, *, stale=False):
    PlanMeterReading.objects.all().delete()
    for provider, used in (("codex", codex), ("claude-code", claude)):
        reading = PlanMeterReading.objects.create(
            provider=provider, account=".x", week_percent=used
        )
        if stale:
            PlanMeterReading.objects.filter(pk=reading.pk).update(
                created_at=timezone.now() - timedelta(hours=2)
            )


def test_the_factory_is_off_unless_told_otherwise(settings):
    settings.FACTORY_ENABLED = False
    assert factory.tick()["started"] is None
    assert "off" in factory.tick()["reason"]


def test_a_paused_factory_reports_but_starts_nothing_and_says_so(almonium):
    meters()
    factory.set_running(False)

    result = factory.tick()

    assert result["started"] is None and "paused" in result["reason"]
    assert not SourceDownload.objects.exists()
    assert factory.switch().tick_note == result["reason"]


def test_the_factory_is_paused_until_first_started(settings):
    from almonium_book_processor.catalog.models import FactorySwitch

    FactorySwitch.objects.all().delete()
    assert factory.switch().running is False


def test_the_queue_lists_every_book_under_way_with_its_pause(almonium):
    from almonium_book_processor.catalog.production import pause_book

    meters()
    factory.tick()
    by_hand = Edition.objects.create(
        work=Work.objects.create(slug="by-hand", title="By hand", author="A"),
        slug="by-hand-en",
        language="en",
        status=Edition.Status.READY,
    )
    PipelineRun.objects.create(
        edition=by_hand,
        stage=PipelineRun.Stage.ADAPT,
        processor_version=PRODUCTION_VERSION,
        input_hash="",
        idempotency_key="by-hand",
        status=PipelineRun.Status.RUNNING,
        summary={
            "levels": ["B2"],
            "tracks": {"levels": {"targets": ["B2"], "index": 0, "step": "write", "since": ""}},
        },
    )
    pause_book(by_hand.id)

    rows = factory.queue()

    assert [(row["step"], row["paused"]) for row in rows] == [
        ("downloading", False),
        ("write (B2)", True),
    ]


def test_a_want_in_another_language_starts_a_translation_of_the_free_text(almonium):
    meters()

    result = factory.tick()

    assert result["started"] == Edition.objects.get().slug
    download = SourceDownload.objects.get()
    assert download.external_id == almonium.preparation_id
    assert download.production == {"levels": [], "languages": ["uk"]}
    assert download.download_url == SOURCE["downloadUrl"]
    reserved = [payload for path, payload in almonium.posts if path == factory.PREPARATIONS_PATH]
    assert reserved == [{"catalogWorkId": WORK_ID, "language": "UK", "sourceId": SOURCE["id"]}]
    # Almonium hears at once how the book stands
    assert almonium.reports()[-1]["phase"] == "downloading"


def test_a_want_in_the_texts_own_language_makes_the_levels(almonium):
    meters()
    almonium.queue = [{**ROW, "language": "EN"}]

    factory.tick()

    assert SourceDownload.objects.get().production == {"levels": ["B2", "B1"], "languages": []}


def test_nothing_starts_without_room_on_both_plans(almonium):
    meters(codex=90)
    assert "Codex" in factory.tick()["reason"]
    meters(claude=86)
    assert "Claude" in factory.tick()["reason"]
    meters(stale=True)
    assert "fresh" in factory.tick()["reason"]
    assert not SourceDownload.objects.exists()


def test_a_paused_account_is_no_room_however_empty_its_week(almonium):
    from almonium_book_processor.catalog.models import PlanAccountPause

    meters(codex=5)
    PlanAccountPause.objects.create(provider="codex", account=".x")

    assert "No open Codex account" in factory.tick()["reason"]
    assert not SourceDownload.objects.exists()


def test_nothing_starts_while_enough_books_are_under_way(almonium, settings):
    meters()
    settings.FACTORY_MAX_PRODUCTIONS = 1
    factory.tick()
    assert SourceDownload.objects.count() == 1

    result = factory.tick()

    assert result["started"] is None
    assert "under way" in result["reason"]
    assert SourceDownload.objects.count() == 1


def test_a_row_whose_text_the_processor_does_not_read_is_passed_over(almonium):
    meters()
    almonium.queue = [{**ROW, "source": {**SOURCE, "language": "la"}}, {**ROW, "title": "Second"}]

    factory.tick()

    assert Edition.objects.get().title == "Second"


def test_a_refused_reservation_does_not_stop_the_tick(almonium, monkeypatch):
    meters()

    def refuse(path, payload, *, failure):
        if path == factory.PREPARATIONS_PATH:
            raise PublicationError("Nobody is waiting on this one any more.")
        return almonium(path, payload, failure=failure)

    monkeypatch.setattr(factory, "_signed_post", refuse)
    result = factory.tick()

    assert result["started"] is None
    assert not SourceDownload.objects.exists()


def shelf_edition(production=None, status=Edition.Status.READY, slug="dracula"):
    work = Work.objects.create(slug=slug, title="Dracula", author="Bram Stoker")
    edition = Edition.objects.create(
        work=work, slug=f"{slug}-en", language="en", status=status, cefr_level="C1"
    )
    SourceDownload.objects.create(
        edition=edition,
        external_id=uuid.uuid4(),
        source_kind="gutenberg",
        source_page_url=SOURCE["pageUrl"],
        download_url=SOURCE["downloadUrl"],
        status=SourceDownload.Status.DOWNLOADED,
        production=production or {},
    )
    return edition


def test_the_text_on_the_shelf_starts_the_production_it_was_fetched_for(settings, monkeypatch):
    settings.FACTORY_PROMOTE_TO = "staging"
    monkeypatch.setattr(
        "almonium_book_processor.catalog.tasks.produce_edition.delay", lambda run_id: None
    )
    edition = shelf_edition({"levels": [], "languages": ["uk"]})

    run = factory.continue_production(edition)

    assert run.summary["languages"] == ["uk"]
    assert run.summary["promote_to"] == "staging" and run.summary["publish"] is True
    # an ingest that stops at the shelf starts nothing
    assert factory.continue_production(shelf_edition(slug="carmilla")) is None


def test_the_status_reported_carries_the_productions_word(settings):
    settings.FACTORY_PROMOTE_TO = "staging"
    edition = shelf_edition({"levels": ["B1"], "languages": []})
    assert factory.preparation_status(edition)["phase"] == "ready"  # not started yet
    run = PipelineRun.objects.create(
        edition=edition,
        stage=PipelineRun.Stage.ADAPT,
        processor_version=PRODUCTION_VERSION,
        input_hash="",
        idempotency_key="p1",
        status=PipelineRun.Status.RUNNING,
    )
    assert factory.preparation_status(edition)["phase"] == "producing"
    assert edition in factory.under_way()
    run.status = PipelineRun.Status.FAILED
    run.error = "B1 held: the probe failed."
    run.save()
    status = factory.preparation_status(edition)
    assert status["phase"] == "failed" and "held" in status["error"]
    assert edition not in factory.under_way()
    run.status = PipelineRun.Status.SUCCEEDED
    run.error = ""
    run.save()
    assert factory.preparation_status(edition)["phase"] == "published"


def test_reporting_stops_once_a_book_is_finished(almonium, settings):
    settings.FACTORY_PROMOTE_TO = ""
    edition = shelf_edition()  # stops at the shelf, ready

    assert factory.report_preparations() == 1
    assert SourceDownload.objects.get().reported_final
    assert factory.report_preparations() == 0
    assert almonium.reports()[-1]["edition_id"] == str(edition.id)


def test_the_dashboard_starts_and_pauses_the_factory_and_a_book(client, settings):
    from django.contrib.auth import get_user_model
    from django.urls import reverse

    from almonium_book_processor.catalog.models import BookPause

    settings.FACTORY_ENABLED = True
    client.force_login(get_user_model().objects.create_user("staff", is_staff=True))
    assert "Start factory" in client.get(reverse("catalog:dashboard")).content.decode()

    client.post(reverse("catalog:factory-switch"), {"action": "start"})
    assert factory.switch().running and factory.switch().changed_by == "staff"
    assert "Pause factory" in client.get(reverse("catalog:dashboard")).content.decode()

    work = Work.objects.create(slug="paused", title="Paused", author="A")
    source = Edition.objects.create(work=work, slug="paused-en", language="en")
    client.post(reverse("catalog:book-pause", args=[source.id]), {"action": "pause"})
    assert BookPause.objects.filter(edition=source).exists()
    client.post(reverse("catalog:book-pause", args=[source.id]), {"action": "resume"})
    assert not BookPause.objects.filter(edition=source).exists()

    PipelineRun.objects.create(
        edition=source,
        stage=PipelineRun.Stage.ADAPT,
        processor_version=PRODUCTION_VERSION,
        input_hash="",
        idempotency_key="paused",
        status=PipelineRun.Status.RUNNING,
        summary={"levels": ["B2"]},
    )
    client.post(reverse("catalog:factory-switch"), {"action": "pause-books"})
    assert BookPause.objects.filter(edition=source).exists()
    assert "1 paused" in client.get(reverse("catalog:dashboard")).content.decode()
    client.post(reverse("catalog:factory-switch"), {"action": "resume-books"})
    assert not BookPause.objects.exists()


def test_a_second_want_for_a_text_on_the_shelf_does_not_fetch_it_again(almonium):
    """Candide and Marianela were fetched twice on 17 October 2026, once per wanted language."""

    meters()
    almonium.queue = [{**ROW, "language": "EN"}]
    factory.tick()
    assert SourceDownload.objects.count() == 1

    almonium.queue = [ROW]  # the same book, wanted in Ukrainian
    almonium.preparation_id = uuid.uuid4()
    result = factory.tick()

    assert result["started"] is None
    assert SourceDownload.objects.count() == 1 and Edition.objects.count() == 1
    reserved = [payload for path, payload in almonium.posts if path == factory.PREPARATIONS_PATH]
    assert len(reserved) == 1  # the second want was not reserved either


class Readers:
    """Stands in for the environment the readers are in: what it offers, and what was pulled."""

    def __init__(self, entries):
        self.entries = entries
        self.pulled = []

    def __call__(self, target):
        return self

    def exports(self):
        return {"origin": "staging.example.test", "editions": self.entries}

    def pull(self, slug):
        self.pulled.append(slug)
        return b"bundle"


def opened_book(monkeypatch, slug="looking-glass", **entry):
    """A book a reader opened there, offered for its levels, landing here when pulled."""

    work = Work.objects.create(slug=slug, title="Through the Looking-Glass", author="L. Carroll")
    edition = Edition.objects.create(
        work=work,
        slug=f"{slug}-en",
        title="Through the Looking-Glass",
        language="en",
        status=Edition.Status.READY,
    )
    readers = Readers(
        [
            {
                "slug": edition.slug,
                "id": str(edition.id),
                "language": "en",
                "awaiting_levels": True,
                **entry,
            }
        ]
    )
    monkeypatch.setattr(factory, "PromotionClient", readers)
    monkeypatch.setattr(factory, "promotion_target", lambda name: name or None)
    monkeypatch.setattr(factory, "source_compatibility_problem", lambda listing: "")
    monkeypatch.setattr(factory, "import_bundle", lambda data, origin=None: {})
    monkeypatch.setattr(
        "almonium_book_processor.catalog.tasks.produce_edition.delay", lambda run_id: None
    )
    return edition, readers


def test_a_book_a_reader_opened_gets_its_levels_before_the_next_wanted_book(almonium, monkeypatch):
    meters()
    edition, readers = opened_book(monkeypatch)

    result = factory.tick()

    assert result["started"] == edition.slug and "levels" in result["reason"]
    assert readers.pulled == [edition.slug]
    run = edition.pipeline_runs.get(processor_version=PRODUCTION_VERSION)
    assert run.summary["levels"] == ["B2", "B1"] and run.summary["origin"] == factory.LIVE
    assert run.summary["promote_to"] == "staging" and run.summary["publish"] is True
    # the wanted queue was not read this tick, and the book counts as one under way
    assert not SourceDownload.objects.exists()
    assert factory.live_under_way() == [edition]

    # tried once: the next tick leaves it and goes on to the wanted queue
    result = factory.tick()

    assert readers.pulled == [edition.slug]
    assert result["started"] != edition.slug and SourceDownload.objects.count() == 1


def test_a_rated_book_and_an_unreadable_one_are_not_pulled(almonium, monkeypatch):
    meters()
    _, readers = opened_book(monkeypatch, awaiting_levels=False)
    readers.entries.append({**readers.entries[0], "awaiting_levels": True, "language": "la"})

    factory.tick()

    assert readers.pulled == []
    assert SourceDownload.objects.count() == 1


def test_readers_that_cannot_be_asked_do_not_stop_the_wanted_queue(almonium, monkeypatch):
    from almonium_book_processor.catalog.promotion import PromotionError

    meters()
    _, readers = opened_book(monkeypatch)

    def unreachable():
        raise PromotionError("Could not ask staging what it offers")

    readers.exports = unreachable

    result = factory.tick()

    assert result["started"] is not None
    assert SourceDownload.objects.count() == 1
