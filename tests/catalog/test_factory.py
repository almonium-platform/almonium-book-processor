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
