from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.test import Client
from django.urls import reverse
from rest_framework.test import APIClient

from almonium_book_processor.catalog.models import (
    AIRun,
    Chapter,
    ContentBlock,
    Edition,
    EditionTombstone,
    ModelConfiguration,
    PipelineRun,
    PromptTemplate,
    QAWarning,
    Work,
)
from almonium_book_processor.catalog.purge import purge_edition
from almonium_book_processor.catalog.spend import ai_spend

SECRET = "test-shared-secret"

pytestmark = pytest.mark.django_db


def build_edition(*, status=Edition.Status.READY, visibility=Work.Visibility.PUBLIC, **extra):
    work = Work.objects.create(
        slug=f"work-{uuid.uuid4().hex[:8]}",
        title="Doomed Work",
        author="Ada Author",
        original_language="de",
        visibility=visibility,
        owner_id=uuid.uuid4() if visibility == Work.Visibility.PRIVATE else None,
    )
    edition = Edition.objects.create(
        slug=f"edition-{uuid.uuid4().hex[:8]}",
        work=work,
        title="Doomed Book",
        author="Ada Author",
        language="de",
        status=status,
        word_count=1234,
        source_sha256="a" * 64,
        **extra,
    )
    edition.source_file.save("doomed.epub", ContentFile(b"epub bytes"), save=True)
    chapter = Chapter.objects.create(edition=edition, sequence=0, title="Eins")
    ContentBlock.objects.create(
        edition=edition,
        chapter=chapter,
        block_id="b1",
        sequence=0,
        block_type="paragraph",
        text="Der erste Abschnitt.",
    )
    QAWarning.objects.create(
        edition=edition, code="empty_spine_document", severity="warning", message="x"
    )
    return edition


def build_ai_run(edition, *, cost="1.500000"):
    configuration = ModelConfiguration.objects.create(
        name=f"config-{uuid.uuid4().hex[:8]}",
        provider="openai",
        model="gpt-test",
        purpose="translation",
    )
    template = PromptTemplate.objects.create(
        name=f"prompt-{uuid.uuid4().hex[:8]}",
        version=1,
        purpose="translation",
        system_prompt="s",
        user_template="u",
    )
    run = PipelineRun.objects.create(
        edition=edition,
        stage=PipelineRun.Stage.TRANSLATE,
        status=PipelineRun.Status.SUCCEEDED,
        idempotency_key=f"{edition.id}:translate",
        processor_version="test",
        input_hash="b" * 64,
    )
    return AIRun.objects.create(
        edition=edition,
        pipeline_run=run,
        model_configuration=configuration,
        prompt_template=template,
        status=AIRun.Status.SUCCEEDED,
        input_tokens=1000,
        output_tokens=500,
        estimated_cost_usd=Decimal(cost),
        request_payload={"prompt": "Der erste Abschnitt."},
        response_payload={"text": "The first passage."},
    )


def test_purge_destroys_the_content_and_the_uploaded_file(
    django_capture_on_commit_callbacks,
) -> None:
    edition = build_edition()
    storage = edition.source_file.storage
    source_name = edition.source_file.name
    edition_slug = edition.slug
    work_id = edition.work_id

    with django_capture_on_commit_callbacks(execute=True):
        tombstone = purge_edition(
            edition, reason=EditionTombstone.Reason.COPYRIGHT, notes="DMCA 12"
        )

    assert not Edition.objects.filter(id=tombstone.edition_id).exists()
    assert not ContentBlock.objects.exists()
    assert not Chapter.objects.exists()
    assert not QAWarning.objects.exists()
    assert not PipelineRun.objects.exists()
    assert not storage.exists(source_name)
    # The work existed only for this edition.
    assert not Work.objects.filter(id=work_id).exists()
    assert (tombstone.edition_slug, tombstone.title, tombstone.reason) == (
        edition_slug,
        "Doomed Book",
        "copyright",
    )
    assert tombstone.source_sha256 == "a" * 64
    assert tombstone.notes == "DMCA 12"


def test_the_spend_ledger_survives_the_book_it_paid_for() -> None:
    edition = build_edition()
    ai_run = build_ai_run(edition)
    before = ai_spend(
        ai_run.created_at.replace(year=ai_run.created_at.year - 1),
        ai_run.created_at.replace(year=ai_run.created_at.year + 1),
    )

    tombstone = purge_edition(edition, reason=EditionTombstone.Reason.COPYRIGHT)

    ai_run.refresh_from_db()
    assert ai_run.edition_id is None
    assert ai_run.pipeline_run_id is None
    assert ai_run.tombstone_id == tombstone.id
    assert ai_run.estimated_cost_usd == Decimal("1.500000")
    assert ai_run.input_tokens == 1000
    # The payloads carried the book's own words; the counts did not.
    assert ai_run.request_payload == {}
    assert ai_run.response_payload == {}
    after = ai_spend(
        ai_run.created_at.replace(year=ai_run.created_at.year - 1),
        ai_run.created_at.replace(year=ai_run.created_at.year + 1),
    )
    assert after["lines"] == before["lines"]


def test_a_published_edition_is_not_purged_behind_the_products_back() -> None:
    edition = build_edition(status=Edition.Status.PUBLISHED, published_book_id=uuid.uuid4())

    with pytest.raises(ValueError, match="Withdraw this edition"):
        purge_edition(edition, reason=EditionTombstone.Reason.COPYRIGHT)

    assert Edition.objects.filter(id=edition.id).exists()


def test_an_edition_other_editions_were_generated_from_is_kept() -> None:
    original = build_edition()
    Edition.objects.create(
        slug="derived-en",
        work=original.work,
        source_edition=original,
        title="Doomed Book",
        author="Ada Author",
        language="en",
        edition_type=Edition.EditionType.MACHINE_TRANSLATION,
    )

    with pytest.raises(ValueError, match="Purge the editions generated from this one first"):
        purge_edition(original, reason=EditionTombstone.Reason.MISTAKE)


def test_a_shared_work_outlives_one_of_its_editions() -> None:
    first = build_edition()
    second = Edition.objects.create(
        slug="second-en",
        work=first.work,
        title="Doomed Book",
        author="Ada Author",
        language="en",
        edition_type=Edition.EditionType.HUMAN_TRANSLATION,
    )

    purge_edition(second, reason=EditionTombstone.Reason.MISTAKE)

    assert Work.objects.filter(id=first.work_id).exists()
    assert Edition.objects.filter(id=first.id).exists()


def test_staff_purge_requires_the_edition_slug_typed_back() -> None:
    edition = build_edition()
    staff = get_user_model().objects.create_user(
        username="purger", password="safe-test-password", is_staff=True
    )
    client = Client()
    client.force_login(staff)
    url = reverse("catalog:purge-edition", args=[edition.id])

    refused = client.post(url, {"reason": "copyright", "notes": "", "confirm_slug": "wrong"})

    assert refused.status_code == 302
    assert Edition.objects.filter(id=edition.id).exists()

    accepted = client.post(url, {"reason": "copyright", "notes": "", "confirm_slug": edition.slug})

    assert accepted.status_code == 302
    assert not Edition.objects.filter(id=edition.id).exists()
    tombstone = EditionTombstone.objects.get(edition_id=edition.id)
    assert tombstone.purged_by == staff


def test_a_published_edition_is_withdrawn_through_the_product_api(monkeypatch) -> None:
    edition = build_edition(status=Edition.Status.PUBLISHED, published_book_id=uuid.uuid4())
    staff = get_user_model().objects.create_user(
        username="withdrawer", password="safe-test-password", is_staff=True
    )
    client = Client()
    client.force_login(staff)
    queued: dict = {}

    def fake_delay(edition_id, **kwargs):
        queued["edition_id"] = edition_id
        queued.update(kwargs)

    monkeypatch.setattr("almonium_book_processor.catalog.views.withdraw_edition.delay", fake_delay)

    response = client.post(
        reverse("catalog:purge-edition", args=[edition.id]),
        {"reason": "copyright", "notes": "DMCA 12", "confirm_slug": edition.slug},
    )

    assert response.status_code == 302
    assert queued == {
        "edition_id": str(edition.id),
        "reason": "copyright",
        "notes": "DMCA 12",
        "actor_id": staff.pk,
    }
    # Nothing is destroyed until Almonium confirms it stopped serving the book.
    assert Edition.objects.filter(id=edition.id).exists()


def test_the_withdrawal_task_tells_almonium_before_it_destroys_anything(monkeypatch) -> None:
    edition = build_edition(status=Edition.Status.PUBLISHED, published_book_id=uuid.uuid4())
    calls: list[str] = []

    def fake_withdraw(target):
        calls.append("withdrawn")
        assert Edition.objects.filter(id=target.id).exists()
        return True

    monkeypatch.setattr(
        "almonium_book_processor.catalog.tasks.withdraw_from_almonium", fake_withdraw
    )
    from almonium_book_processor.catalog.tasks import withdraw_edition

    withdraw_edition.run(str(edition.id), reason="copyright", notes="DMCA 12")

    assert calls == ["withdrawn"]
    assert not Edition.objects.filter(id=edition.id).exists()
    tombstone = EditionTombstone.objects.get(edition_id=edition.id)
    assert tombstone.was_published is True
    assert tombstone.published_book_id == edition.published_book_id


def test_a_failed_withdrawal_leaves_the_book_intact(monkeypatch) -> None:
    edition = build_edition(status=Edition.Status.PUBLISHED, published_book_id=uuid.uuid4())

    def fake_withdraw(target):
        raise RuntimeError("Almonium withdrawal failed.")

    monkeypatch.setattr(
        "almonium_book_processor.catalog.tasks.withdraw_from_almonium", fake_withdraw
    )
    from almonium_book_processor.catalog.tasks import withdraw_edition

    with pytest.raises(RuntimeError):
        withdraw_edition.run(str(edition.id), reason="copyright")

    assert Edition.objects.filter(id=edition.id).exists()
    assert not EditionTombstone.objects.exists()


def test_an_owner_can_delete_their_own_private_import(monkeypatch) -> None:
    monkeypatch.setenv("ALMONIUM_BOOKS_PUBLISHER_TOKEN", SECRET)
    edition = build_edition(visibility=Work.Visibility.PRIVATE)
    owner_id = edition.work.owner_id

    response = APIClient().delete(
        f"/api/v1/internal/imports/{edition.id}/?owner_id={owner_id}",
        HTTP_X_ALMONIUM_BOOKS_TOKEN=SECRET,
    )

    assert response.status_code == 204
    assert not Edition.objects.filter(id=edition.id).exists()
    assert EditionTombstone.objects.get(edition_id=edition.id).reason == "owner_request"


def test_one_owner_cannot_delete_another_owners_import(monkeypatch) -> None:
    monkeypatch.setenv("ALMONIUM_BOOKS_PUBLISHER_TOKEN", SECRET)
    edition = build_edition(visibility=Work.Visibility.PRIVATE)

    response = APIClient().delete(
        f"/api/v1/internal/imports/{edition.id}/?owner_id={uuid.uuid4()}",
        HTTP_X_ALMONIUM_BOOKS_TOKEN=SECRET,
    )

    assert response.status_code == 404
    assert Edition.objects.filter(id=edition.id).exists()


def test_the_withdrawal_request_is_signed_like_a_publication(monkeypatch) -> None:
    import hashlib
    import hmac
    import json

    from almonium_book_processor.catalog import publication

    monkeypatch.setenv("ALMONIUM_API_URL", "https://api.example.test")
    monkeypatch.setenv("ALMONIUM_BOOKS_PUBLISHER_TOKEN", SECRET)
    edition = build_edition(status=Edition.Status.PUBLISHED, published_book_id=uuid.uuid4())
    sent: dict = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return json.dumps({"withdrawn": True}).encode()

    def fake_urlopen(request, timeout=None):
        sent["url"] = request.full_url
        sent["method"] = request.method
        sent["body"] = request.data
        sent["headers"] = {key.lower(): value for key, value in request.headers.items()}
        return FakeResponse()

    monkeypatch.setattr(publication, "urlopen", fake_urlopen)

    assert publication.withdraw_from_almonium(edition) is True

    assert sent["url"] == "https://api.example.test/internal/books/publications/withdrawals"
    assert sent["method"] == "POST"
    assert json.loads(sent["body"]) == {"editionSlug": edition.slug}
    timestamp = sent["headers"]["x-almonium-books-timestamp"]
    expected = hmac.new(
        SECRET.encode(), f"{timestamp}.".encode() + sent["body"], hashlib.sha256
    ).hexdigest()
    assert sent["headers"]["x-almonium-books-signature"] == expected


def test_the_panel_offers_withdrawal_for_a_published_edition() -> None:
    edition = build_edition(status=Edition.Status.PUBLISHED, published_book_id=uuid.uuid4())
    staff = get_user_model().objects.create_user(
        username="panel-editor", password="safe-test-password", is_staff=True
    )
    client = Client()
    client.force_login(staff)

    detail = client.get(reverse("catalog:edition-detail", args=[edition.id])).content.decode()

    assert "Withdraw and purge" in detail
    assert "keeping every reader" in detail


def test_the_panel_refuses_while_generated_editions_depend_on_this_one() -> None:
    original = build_edition()
    Edition.objects.create(
        slug="blocked-derived-en",
        work=original.work,
        source_edition=original,
        title="Doomed Book",
        author="Ada Author",
        language="en",
        edition_type=Edition.EditionType.MACHINE_TRANSLATION,
    )
    staff = get_user_model().objects.create_user(
        username="blocked-editor", password="safe-test-password", is_staff=True
    )
    client = Client()
    client.force_login(staff)

    detail = client.get(reverse("catalog:edition-detail", args=[original.id])).content.decode()

    assert "Editions generated from this one must go first" in detail
    assert "Purge this edition</button>" not in detail

    response = client.post(
        reverse("catalog:purge-edition", args=[original.id]),
        {"reason": "copyright", "notes": "", "confirm_slug": original.slug},
    )

    assert response.status_code == 302
    assert Edition.objects.filter(id=original.id).exists()


def staff_client(username):
    staff = get_user_model().objects.create_user(
        username=username, password="safe-test-password", is_staff=True
    )
    client = Client()
    client.force_login(staff)
    return client, staff


def test_the_removed_books_page_shows_what_a_purge_left_behind() -> None:
    edition = build_edition()
    build_ai_run(edition)
    client, staff = staff_client("auditor")
    purge_edition(edition, reason=EditionTombstone.Reason.COPYRIGHT, notes="DMCA 12", actor=staff)

    page = client.get(reverse("catalog:removed-books")).content.decode()

    assert "Doomed Book" in page
    assert "Copyright claim" in page
    assert "DMCA 12" in page
    assert "auditor" in page
    # The ledger row the purge kept is summed against the tombstone it points at.
    assert "$1.5000" in page


def test_the_removed_books_page_is_staff_only() -> None:
    response = Client().get(reverse("catalog:removed-books"))

    assert response.status_code == 302
    assert "/admin/login/" in response["Location"]


def test_a_purge_lands_the_operator_on_the_record_it_just_created() -> None:
    edition = build_edition()
    client, _ = staff_client("purge-redirect")

    response = client.post(
        reverse("catalog:purge-edition", args=[edition.id]),
        {"reason": "mistake", "notes": "", "confirm_slug": edition.slug},
    )

    assert response["Location"] == reverse("catalog:removed-books")


def test_a_queued_withdrawal_is_visible_before_almonium_confirms(monkeypatch) -> None:
    edition = build_edition(status=Edition.Status.PUBLISHED, published_book_id=uuid.uuid4())
    client, staff = staff_client("withdrawal-watcher")
    monkeypatch.setattr(
        "almonium_book_processor.catalog.views.withdraw_edition.delay",
        lambda *args, **kwargs: None,
    )

    response = client.post(
        reverse("catalog:purge-edition", args=[edition.id]),
        {"reason": "copyright", "notes": "DMCA 12", "confirm_slug": edition.slug},
    )

    assert response["Location"] == reverse("catalog:removed-books")
    edition.refresh_from_db()
    assert edition.withdrawal_requested_at is not None
    assert edition.withdrawal_requested_by == staff
    assert edition.withdrawal_reason == "copyright"
    # Nothing was destroyed, so the only trace of the removal is the request.
    page = client.get(reverse("catalog:removed-books")).content.decode()
    assert "Withdrawals in flight" in page
    assert "Doomed Book" in page
    assert "withdrawal-watcher" in page
    assert not EditionTombstone.objects.exists()


def test_a_completed_withdrawal_leaves_the_in_flight_list_for_a_tombstone(monkeypatch) -> None:
    edition = build_edition(status=Edition.Status.PUBLISHED, published_book_id=uuid.uuid4())
    client, _ = staff_client("withdrawal-finisher")
    monkeypatch.setattr(
        "almonium_book_processor.catalog.views.withdraw_edition.delay",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        "almonium_book_processor.catalog.tasks.withdraw_from_almonium", lambda target: True
    )
    client.post(
        reverse("catalog:purge-edition", args=[edition.id]),
        {"reason": "copyright", "notes": "DMCA 12", "confirm_slug": edition.slug},
    )
    from almonium_book_processor.catalog.tasks import withdraw_edition

    withdraw_edition.run(str(edition.id), reason="copyright", notes="DMCA 12")

    page = client.get(reverse("catalog:removed-books")).content.decode()
    assert "Withdrawals in flight" not in page
    assert "Withdrawn from Almonium" in page
    assert EditionTombstone.objects.get(edition_id=edition.id).was_published is True
