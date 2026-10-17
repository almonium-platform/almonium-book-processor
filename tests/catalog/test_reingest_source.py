"""reingest_source rebuilds a downloaded book's chapters from the stored file."""

from __future__ import annotations

import uuid
from io import StringIO

import pytest
from django.core.files.base import ContentFile
from django.core.management import CommandError, call_command

from almonium_book_processor.catalog import tasks
from almonium_book_processor.catalog.models import (
    Chapter,
    ContentBlock,
    Edition,
    EditionTombstone,
    PipelineRun,
    SourceDownload,
    Work,
)

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def media_root(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path


@pytest.fixture
def queued(monkeypatch):
    log: list[str] = []
    monkeypatch.setattr(tasks.process_book_pipeline, "delay", log.append)
    return log


def source_ingest(*, status=Edition.Status.READY) -> Edition:
    work = Work.objects.create(
        slug=f"work-{uuid.uuid4().hex[:8]}",
        title="Marianela",
        author="Benito Pérez Galdós",
        original_language="es",
    )
    edition = Edition.objects.create(
        slug=f"marianela-{uuid.uuid4().hex[:8]}",
        work=work,
        title="Marianela",
        author="Benito Pérez Galdós",
        language="es",
        status=status,
        word_count=50_000,
    )
    edition.source_file.save("source.epub", ContentFile(b"PK\x03\x04 epub"), save=True)
    SourceDownload.objects.create(
        edition=edition,
        external_id=uuid.uuid4(),
        source_kind=SourceDownload.Kind.GUTENBERG,
        source_page_url="https://www.gutenberg.org/ebooks/17340",
        download_url="https://www.gutenberg.org/ebooks/17340.epub3.images",
        status=SourceDownload.Status.DOWNLOADED,
        reported_final=True,
    )
    chapter = Chapter.objects.create(edition=edition, sequence=0, title="Marianela")
    ContentBlock.objects.create(
        edition=edition,
        chapter=chapter,
        block_id="c0.p1",
        sequence=1,
        block_type="paragraph",
        text="Se puso el sol.",
    )
    PipelineRun.objects.create(
        edition=edition,
        stage=PipelineRun.Stage.INGEST,
        status=PipelineRun.Status.SUCCEEDED,
        idempotency_key=f"{edition.id}:hash:ingest:test",
        processor_version="test",
        input_hash="hash",
    )
    return edition


def derived_from(source: Edition, slug: str, **extra) -> Edition:
    return Edition.objects.create(
        slug=slug,
        work=source.work,
        source_edition=source,
        title=source.title,
        author=source.author,
        language=extra.pop("language", "es"),
        edition_type=extra.pop("edition_type", Edition.EditionType.ADAPTATION),
        cefr_level=extra.pop("cefr_level", "B1"),
        **extra,
    )


def test_the_command_purges_what_was_made_and_queues_the_pipeline_again(
    queued, django_capture_on_commit_callbacks
) -> None:
    edition = source_ingest()
    adaptation = derived_from(edition, "marianela-b1")
    derived_from(
        adaptation,
        "marianela-b1-en",
        language="en",
        edition_type=Edition.EditionType.MACHINE_TRANSLATION,
        cefr_level=None,
    )
    out = StringIO()

    with django_capture_on_commit_callbacks(execute=True):
        call_command("reingest_source", edition.slug, stdout=out)

    edition.refresh_from_db()
    assert queued == [str(edition.id)]
    assert edition.status == Edition.Status.QUEUED
    assert edition.word_count == 0
    assert not edition.chapters.exists()
    assert not edition.pipeline_runs.exists()
    assert edition.source_file  # the stored file is what the pipeline reads again
    assert edition.source_download.reported_final is False
    assert not Edition.objects.filter(slug__in=["marianela-b1", "marianela-b1-en"]).exists()
    assert set(EditionTombstone.objects.values_list("edition_slug", flat=True)) == {
        "marianela-b1",
        "marianela-b1-en",
    }
    assert "purged marianela-b1-en, marianela-b1" in out.getvalue()
    assert "pipeline queued" in out.getvalue()


def test_a_published_derived_edition_stops_the_rebuild(queued) -> None:
    edition = source_ingest()
    derived_from(edition, "marianela-b1-live", status=Edition.Status.PUBLISHED)

    with pytest.raises(CommandError, match="marianela-b1-live.*is published"):
        call_command("reingest_source", edition.slug)

    edition.refresh_from_db()
    assert edition.chapters.exists()
    assert edition.status == Edition.Status.READY
    assert Edition.objects.filter(slug="marianela-b1-live").exists()
    assert queued == []


def test_an_upload_is_not_a_source_ingest(queued) -> None:
    edition = source_ingest()
    edition.source_download.delete()

    with pytest.raises(CommandError, match="was not created by a source ingest"):
        call_command("reingest_source", edition.slug)

    assert queued == []
