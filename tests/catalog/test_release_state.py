import uuid
from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from almonium_book_processor.catalog.models import (
    Chapter,
    ContentBlock,
    ContentBlockRevision,
    Edition,
    EditionArtifact,
    PipelineRun,
    Work,
)
from almonium_book_processor.catalog.release_state import listing_release_state, release_rows
from almonium_book_processor.catalog.tasks import publication_input_hash

pytestmark = pytest.mark.django_db

LONG_AGO = timezone.now() - timedelta(days=2)


@pytest.fixture
def published():
    work = Work.objects.create(slug="release", title="Book", author="Ada", original_language="en")
    original = Edition.objects.create(
        work=work,
        slug="release-en",
        title="Book",
        author="Ada",
        language="en",
        parallel_role="canonical",
        status="published",
        published_at=LONG_AGO,
        source_sha256="a" * 64,
    )
    adapted = Edition.objects.create(
        work=work,
        slug="release-en-b2",
        title="Book",
        author="Ada",
        language="en",
        cefr_level="B2",
        edition_type="adaptation",
        source_edition=original,
        parallel_role="parallel",
        status="published",
        published_at=LONG_AGO,
        source_sha256="b" * 64,
    )
    for edition in (original, adapted):
        chapter = Chapter.objects.create(edition=edition, sequence=1, title="I")
        ContentBlock.objects.create(
            edition=edition, chapter=chapter, block_id="c1.p1", sequence=1, text="Hello."
        )
        PipelineRun.objects.create(
            edition=edition,
            stage="publish",
            status="succeeded",
            idempotency_key=f"{edition.id}:publish",
            processor_version="t",
            input_hash=publication_input_hash(edition),
        )
    return original, adapted


def promote(edition, target, status="succeeded", when=LONG_AGO):
    run = PipelineRun.objects.create(
        edition=edition,
        stage="promote",
        status=status,
        idempotency_key=f"{edition.id}:promote:{target}:{uuid.uuid4().hex}",
        processor_version="t",
        input_hash="",
        summary={"target": target, "publish": True},
        finished_at=when if status == "succeeded" else None,
    )
    PipelineRun.objects.filter(pk=run.pk).update(created_at=when)
    return run


def tokens(edition):
    return [
        (token.target, token.state) for token in listing_release_state([edition])[edition.id].tokens
    ]


def correct(edition):
    block = edition.blocks.get()
    ContentBlockRevision.objects.create(
        edition=edition,
        block=block,
        stable_block_id=block.block_id,
        previous_text=block.text,
        revised_text="Hullo.",
    )


def test_local_row_is_current_until_published_metadata_changes(published):
    original, adapted = published
    (row,) = release_rows(adapted)
    assert (row["target"], row["state"], row["metadata_behind"]) == ("here", "current", False)

    correct(adapted)
    (row,) = release_rows(adapted)
    # The text is read live, so a correction alone leaves this environment current.
    assert (row["state"], row["corrections"]) == ("current", 1)

    adapted.title = "Book, adapted"
    adapted.save()
    (row,) = release_rows(adapted)
    assert (row["state"], row["metadata_behind"]) == ("behind", True)
    assert listing_release_state([adapted])[adapted.id].metadata_behind is True


def test_promotion_target_falls_behind_when_the_chain_changes(published, monkeypatch):
    original, adapted = published
    promote(adapted, "staging")
    rows = {row["target"]: row for row in release_rows(adapted)}
    assert rows["staging"]["state"] == "current"
    assert rows["staging"]["published_there"] is True
    assert tokens(adapted) == [("staging", "current")]

    # A correction to the source travels in the adaptation's bundle too.
    correct(original)
    EditionArtifact.objects.create(
        edition=adapted, kind="lexical_profile", input_hash="x", processor_version="v"
    )
    rows = {row["target"]: row for row in release_rows(adapted)}
    assert (
        rows["staging"]["state"],
        rows["staging"]["corrections"],
        rows["staging"]["artifacts"],
    ) == (
        "behind",
        1,
        1,
    )
    assert tokens(adapted) == [("staging", "behind")]

    promote(adapted, "staging", when=timezone.now())
    rows = {row["target"]: row for row in release_rows(adapted)}
    assert rows["staging"]["state"] == "current"
    assert tokens(adapted) == [("staging", "current")]


def test_configured_targets_and_pending_or_failed_promotions_are_listed(published, monkeypatch):
    original, adapted = published
    monkeypatch.setattr(
        "almonium_book_processor.catalog.promotion.promotion_targets",
        lambda: [type("T", (), {"name": "production"})()],
    )
    promote(adapted, "staging", status="failed", when=timezone.now())
    promote(adapted, "production", status="queued", when=timezone.now())
    rows = {row["target"]: row for row in release_rows(adapted)}
    assert rows["production"]["state"] == "running"
    assert rows["staging"]["state"] == "never"
    assert rows["staging"]["run"].status == "failed"
    # The listing says the same in token form: configured targets first.
    assert tokens(adapted) == [("production", "queued"), ("staging", "failed")]
    (state,) = listing_release_state([adapted]).values()
    assert state.tokens[1].title.startswith("The last promotion to staging failed")


def test_tokens_wait_for_approval_unless_something_already_went_out(published, monkeypatch):
    original, adapted = published
    monkeypatch.setattr(
        "almonium_book_processor.catalog.promotion.promotion_targets",
        lambda: [type("T", (), {"name": "staging"})()],
    )
    Edition.objects.filter(pk=adapted.pk).update(status="review")
    adapted.refresh_from_db()
    assert tokens(adapted) == []
    Edition.objects.filter(pk=adapted.pk).update(status="ready")
    adapted.refresh_from_db()
    assert tokens(adapted) == [("staging", "never")]
    # Sent back to review after a promotion: staging still holds a copy.
    promote(adapted, "staging")
    Edition.objects.filter(pk=adapted.pk).update(status="review")
    adapted.refresh_from_db()
    assert tokens(adapted) == [("staging", "current")]


def test_edition_page_and_dashboard_flag_what_is_behind(client, published):
    original, adapted = published
    promote(adapted, "staging")
    correct(adapted)
    adapted.title = "Book, adapted"
    adapted.save()
    client.force_login(get_user_model().objects.create_user(username="staff", is_staff=True))

    page = client.get(reverse("catalog:edition-detail", args=[adapted.id]))
    assert page.status_code == 200
    assert page.context["release_behind"] == 2
    html = page.content.decode()
    assert "Readers are behind in 2 places" in html
    assert "Update in Almonium" in html
    assert "Promote to staging" in html

    dashboard = client.get(reverse("catalog:dashboard")).content.decode()
    assert "Metadata behind" in dashboard
    assert '<span class="promotion-dot"></span>staging behind</span>' in dashboard
    assert "1 behind on staging" in dashboard


def test_failed_publish_is_shown_where_it_was_queued(client, published):
    original, adapted = published
    adapted.title = "Book, adapted"
    adapted.save()
    PipelineRun.objects.create(
        edition=adapted,
        stage="publish",
        status="failed",
        idempotency_key=f"{adapted.id}:publish:again",
        processor_version="t",
        input_hash=publication_input_hash(adapted),
        error="Almonium publication failed: connection refused.",
    )
    (row,) = release_rows(adapted)
    assert (row["state"], row["metadata_behind"]) == ("behind", True)
    assert row["run"].error == "Almonium publication failed: connection refused."

    client.force_login(get_user_model().objects.create_user(username="staff", is_staff=True))
    page = client.get(reverse("catalog:edition-detail", args=[adapted.id]))
    html = page.content.decode()
    assert "The last metadata update failed: Almonium publication failed" in html
    assert "Last attempt failed: Almonium publication failed" in html
    assert "Update again" in html


def test_failed_first_publish_is_shown_on_a_ready_edition(client, published, monkeypatch):
    original, _ = published
    original.status = "ready"
    original.published_at = None
    original.save()
    monkeypatch.setattr("almonium_book_processor.catalog.views.publication_blocker", lambda e: "")
    original.pipeline_runs.all().delete()
    PipelineRun.objects.create(
        edition=original,
        stage="publish",
        status="failed",
        idempotency_key=f"{original.id}:publish",
        processor_version="t",
        input_hash=publication_input_hash(original),
        error="Almonium publication failed: connection refused.",
    )
    (row,) = release_rows(original)
    assert (row["state"], row["run"].status) == ("unpublished", "failed")

    client.force_login(get_user_model().objects.create_user(username="staff", is_staff=True))
    html = client.get(reverse("catalog:edition-detail", args=[original.id])).content.decode()
    assert "The last publication failed: Almonium publication failed" in html
    assert "Publish again" in html


def test_pending_publish_holds_the_button(published):
    original, adapted = published
    PipelineRun.objects.create(
        edition=adapted,
        stage="publish",
        status="queued",
        idempotency_key=f"{adapted.id}:publish:queued",
        processor_version="t",
        input_hash="x",
    )
    (row,) = release_rows(adapted)
    assert (row["state"], row["run"]) == ("running", None)
