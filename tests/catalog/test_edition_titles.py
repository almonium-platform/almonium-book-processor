"""Titles name the work in the edition's language; the level lives beside them."""

from __future__ import annotations

from importlib import import_module

import pytest
from django.apps import apps
from django.contrib.auth import get_user_model
from django.urls import reverse

from almonium_book_processor.catalog.models import Edition, PipelineRun, Work
from almonium_book_processor.catalog.tasks import publication_input_hash, publication_stale

pytestmark = pytest.mark.django_db


@pytest.fixture
def staff(client):
    user = get_user_model().objects.create_user(username="staff", is_staff=True)
    client.force_login(user)
    return user


@pytest.fixture
def work():
    return Work.objects.create(
        slug="frankenstein",
        title="Frankenstein; or, the Modern Prometheus",
        author="Mary Shelley",
        original_language="en",
        publication_year=1818,
        metadata_confirmed_at="2026-01-01T00:00:00Z",
    )


@pytest.fixture
def original(work):
    return Edition.objects.create(
        work=work,
        slug="frankenstein-en",
        title=work.title,
        author=work.author,
        language="en",
        cefr_level="C1",
        source_sha256="a" * 64,
        status=Edition.Status.PUBLISHED,
    )


@pytest.fixture
def ukrainian(work, original):
    return Edition.objects.create(
        work=work,
        slug="frankenstein-uk",
        source_edition=original,
        title="Франкенштейн, або Сучасний Прометей",
        author="Мері Шеллі",
        language="uk",
        cefr_level="C1",
        edition_type=Edition.EditionType.MACHINE_TRANSLATION,
        parallel_role=Edition.ParallelRole.PARALLEL,
        source_sha256="b" * 64,
        status=Edition.Status.PUBLISHED,
    )


def _published(edition):
    PipelineRun.objects.create(
        edition=edition,
        stage=PipelineRun.Stage.PUBLISH,
        status=PipelineRun.Status.SUCCEEDED,
        processor_version="test",
        input_hash=publication_input_hash(edition),
        idempotency_key=f"{edition.id}:publish:test",
    )


def test_the_original_title_shows_once_in_grey_under_a_translated_title(
    client, staff, original, ukrainian
):
    page = client.get(reverse("catalog:edition-detail", args=[ukrainian.id])).content.decode()
    # The lineage link and the editable work-title field name the source too;
    # the book's own heading names the original exactly once.
    heading = page.split("<body")[1].split('<section class="metrics">')[0]
    assert heading.count("Frankenstein; or, the Modern Prometheus") == 1
    assert '<p class="original-title">Frankenstein; or, the Modern Prometheus</p>' in heading
    assert "<h1>Франкенштейн, або Сучасний Прометей</h1>" in heading
    assert "Мері Шеллі" in heading
    assert '<span class="level-chip">C1</span>' in heading

    page = client.get(reverse("catalog:edition-detail", args=[original.id])).content.decode()
    heading = page.split("<body")[1].split('<section class="metrics">')[0]
    assert "original-title" not in page
    assert heading.count("Frankenstein; or, the Modern Prometheus") == 1
    assert '<span class="level-chip">C1</span>' in heading


def test_the_migration_takes_the_level_out_of_titles_and_localises_the_ukrainian_edition(
    work, original
):
    adaptation = Edition.objects.create(
        work=work,
        slug="frankenstein-en-b2",
        source_edition=original,
        title="Frankenstein; or, the Modern Prometheus — B2 adaptation",
        author="Mary Shelley",
        language="en",
        edition_type=Edition.EditionType.ADAPTATION,
    )
    ukrainian = Edition.objects.create(
        work=work,
        slug="shelley-frankenstein-uk-parallel",
        source_edition=original,
        title="Frankenstein; or, The Modern Prometheus",
        author="Mary Shelley",
        language="uk",
        edition_type=Edition.EditionType.MACHINE_TRANSLATION,
    )
    migration = import_module("almonium_book_processor.catalog.migrations.0028_level_out_of_titles")

    migration.strip_levels_and_localise(apps, None)

    adaptation.refresh_from_db()
    ukrainian.refresh_from_db()
    original.refresh_from_db()
    assert adaptation.title == "Frankenstein; or, the Modern Prometheus"
    assert ukrainian.title == "Франкенштейн, або Сучасний Прометей"
    assert ukrainian.author == "Мері Шеллі"
    assert original.title == work.title and original.author == work.author


def test_a_published_edition_is_stale_once_a_published_value_changes(original):
    # No publish history: nothing here says what Almonium holds, so no nagging.
    assert not publication_stale(original)
    _published(original)
    assert not publication_stale(original)

    original.title = "Frankenstein"
    original.save(update_fields=["title"])

    assert publication_stale(original)


def test_the_page_offers_to_update_almonium_and_the_view_queues_it(
    client, staff, monkeypatch, original
):
    _published(original)
    queued: list[str] = []
    monkeypatch.setattr(
        "almonium_book_processor.catalog.views.publish_edition.delay", queued.append
    )
    monkeypatch.setattr(
        "almonium_book_processor.catalog.views.publication_blocker", lambda edition: ""
    )
    url = reverse("catalog:edition-detail", args=[original.id])
    assert "Update in Almonium" not in client.get(url).content.decode()

    response = client.post(reverse("catalog:publish-edition", args=[original.id]), follow=True)
    assert "already has the current metadata of this edition" in response.content.decode()
    assert queued == []

    Edition.objects.filter(id=original.id).update(title="Frankenstein")
    assert "Update in Almonium" in client.get(url).content.decode()

    response = client.post(reverse("catalog:publish-edition", args=[original.id]), follow=True)
    assert "Update queued" in response.content.decode()
    assert queued == [str(original.id)]


def test_confirming_metadata_on_a_published_edition_updates_almonium(
    client, staff, monkeypatch, original, ukrainian
):
    _published(ukrainian)
    queued: list[str] = []
    monkeypatch.setattr(
        "almonium_book_processor.catalog.views.publish_edition.delay", queued.append
    )
    monkeypatch.setattr(
        "almonium_book_processor.catalog.views.publication_blocker", lambda edition: ""
    )
    form = client.get(reverse("catalog:edition-detail", args=[ukrainian.id])).context[
        "metadata_form"
    ]
    data = {name: value for name, value in form.initial.items() if value not in (None, "")}
    data["edition_title"] = "Франкенштейн"

    response = client.post(
        reverse("catalog:confirm-edition-metadata", args=[ukrainian.id]), data, follow=True
    )

    assert "Almonium is being updated" in response.content.decode()
    assert queued == [str(ukrainian.id)]
    ukrainian.refresh_from_db()
    assert ukrainian.title == "Франкенштейн"
    # The work keeps its own title: a translation does not rename the original.
    assert ukrainian.work.title == "Frankenstein; or, the Modern Prometheus"
