import json
import uuid

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from almonium_book_processor.catalog.book_adaptation import book_plan, queue_book, run_book
from almonium_book_processor.catalog.models import AIRun, Chapter, ContentBlock, Edition, Work

pytestmark = pytest.mark.django_db


@pytest.fixture
def source(settings, monkeypatch):
    settings.OPENAI_API_KEY = "fake"
    settings.OPENAI_TRANSLATION_QUALITY_MODEL = "test-model"
    monkeypatch.setattr("almonium_book_processor.catalog.tasks.adapt_book.delay", lambda _: None)
    monkeypatch.setattr(
        "almonium_book_processor.catalog.tasks.enrich_adapted_book.delay", lambda _: None
    )
    work = Work.objects.create(slug="book-adapt", title="Novel", author="Author")
    edition = Edition.objects.create(
        work=work,
        slug="novel-en",
        title="Novel",
        author="Author",
        language="en",
        cefr_level="C1",
        status="ready",
    )
    for seq in (1, 2, 3, 4):
        chapter = Chapter.objects.create(edition=edition, sequence=seq, title=f"Chapter {seq}")
        ContentBlock.objects.create(
            edition=edition,
            chapter=chapter,
            sequence=1,
            block_id=f"c{seq}.p1",
            align_group=uuid.uuid4(),
            text="He opened the door.",
        )
    return edition


class Provider:
    def __init__(self, fail=None, hook=None):
        self.calls = 0
        self.fail = fail
        self.hook = hook

    def respond(self, body):
        self.calls += 1
        source = json.loads(body["input"])
        blocks = [
            {"block_id": b["block_id"], "text": b["text"], "decision": "kept", "reason": ""}
            for b in source["blocks"]
        ]
        if self.calls == self.fail:
            blocks = []
        if self.hook:
            self.hook()
        return {
            "id": "response",
            "status": "completed",
            "usage": {"input_tokens": 100, "output_tokens": 50},
            "output": [
                {
                    "type": "message",
                    "content": [
                        {
                            "type": "output_text",
                            "text": json.dumps({"blocks": blocks, "review_notes": []}),
                        }
                    ],
                }
            ],
        }


@pytest.mark.parametrize("target_level", ["B1", "B2"])
def test_complete_book_is_separate_aligned_review_only_and_idempotent(source, target_level):
    before = book_plan(source)["source_hash"]
    run = queue_book(source.id, target_level=target_level)
    assert queue_book(source.id, target_level=target_level).id == run.id
    provider = Provider()
    run_book(run.id, provider=provider)
    run_book(run.id, provider=provider)
    target = Edition.objects.get(pk=run.edition_id)
    assert provider.calls == 4
    assert target.blocks.count() == source.blocks.count()
    assert target.chapters.count() == source.chapters.count()
    assert target.cefr_level is None
    # The level is a field and a chip; the title is the work's, untouched.
    assert target.title == source.title and target.author == source.author
    assert target.status == "review"
    assert target.auto_publish is False
    assert target.edition_type == "adaptation"
    assert target.supports_parallel_reading
    assert target.source_edition_id == source.id
    assert target.warnings.filter(code="adaptation_fidelity_review", resolved_at=None).exists()
    assert target.ai_runs.count() == 4
    assert source.ai_runs.count() == 0
    assert target.pipeline_runs.filter(stage="align", status="succeeded").exists()
    for block in target.blocks.all():
        original = source.blocks.get(block_id=block.block_id)
        assert block.align_group == original.align_group
        assert block.attributes["adaptation"]["source_revision"] == before
        assert block.attributes["adaptation"]["decision"] == "kept"
        assert block.attributes["adaptation"]["target_level"] == target_level
    source.refresh_from_db()
    assert source.cefr_level == "C1" and source.status == "ready"
    assert book_plan(source)["source_hash"] == before


@pytest.mark.parametrize("target_level", ["B1", "B2"])
def test_failure_never_creates_partial_book_and_retry_reuses_completed_chunks(source, target_level):
    run = queue_book(source.id, target_level=target_level)
    provider = Provider(fail=2)
    with pytest.raises(ValueError):
        run_book(run.id, provider=provider)
    assert not run.edition.blocks.exists()
    failed = AIRun.objects.get(status="failed")
    assert failed.estimated_cost_usd > 0
    run = queue_book(source.id, target_level=target_level)
    retry = Provider()
    run_book(run.id, provider=retry)
    assert retry.calls == 3  # First chapter is reused; second, third, fourth are generated.
    assert run.edition.blocks.count() == 4
    failed.refresh_from_db()
    assert failed.status == "failed"


def test_windowing_preserves_all_blocks_and_empty_chapters(source, monkeypatch):
    monkeypatch.setattr("almonium_book_processor.catalog.book_adaptation.MAX_CHARS", 25)
    chapter = source.chapters.first()
    ContentBlock.objects.create(
        edition=source,
        chapter=chapter,
        sequence=2,
        block_id="extra",
        text="Another short line.",
        align_group=uuid.uuid4(),
    )
    Chapter.objects.create(edition=source, sequence=5, title="Empty chapter")
    blank = Chapter.objects.create(edition=source, sequence=6, title="Illustration")
    ContentBlock.objects.create(
        edition=source,
        chapter=blank,
        sequence=1,
        block_id="image",
        align_group=uuid.uuid4(),
        block_type="image",
        text="",
        attributes={"src": "cover.jpg"},
    )
    plan = book_plan(source)
    assert len(plan["windows"]) == 6
    run = queue_book(source.id)
    provider = Provider()
    run_book(run.id, provider=provider)
    assert provider.calls == 5  # The empty image block is copied, not sent to AI.
    assert run.edition.blocks.count() == 6
    assert run.edition.chapters.count() == 6
    assert run.edition.blocks.get(block_id="image").attributes["src"] == "cover.jpg"


def test_source_edit_during_generation_prevents_materialization(source):
    run = queue_book(source.id)

    def edit():
        source.blocks.filter(block_id="c4.p1").update(text="Source was revised.")

    with pytest.raises(ValueError, match="Source changed"):
        run_book(run.id, provider=Provider(hook=edit))
    assert not run.edition.blocks.exists()
    assert queue_book(source.id).edition_id != run.edition_id


def test_private_and_oversized_sources_fail_before_creating_target(source):
    source.work.visibility = Work.Visibility.PRIVATE
    source.work.save()
    with pytest.raises(ValueError, match="public"):
        queue_book(source.id)
    source.work.visibility = Work.Visibility.PUBLIC
    source.work.save()
    source.blocks.filter(block_id="c1.p1").update(text="x" * 40001)
    with pytest.raises(ValueError, match="window limit"):
        queue_book(source.id)
    assert Edition.objects.count() == 1
    assert AIRun.objects.count() == 0


def test_staff_route_and_failed_retry_do_not_call_translation(client, source, monkeypatch):
    url = reverse("catalog:queue-book-adaptation", args=[source.id])
    assert client.post(url).status_code == 302
    assert Edition.objects.count() == 1
    user = get_user_model().objects.create_user(username="staff", is_staff=True)
    client.force_login(user)
    assert client.get(url).status_code == 405
    response = client.post(url)
    assert response.status_code == 302
    target = source.derived_editions.get()
    run = target.pipeline_runs.get(processor_version="b2-book-v1")
    with pytest.raises(ValueError):
        run_book(run.id, provider=Provider(fail=1))

    def unexpected(*args, **kwargs):
        pytest.fail("Adaptation must not retry as translation")

    monkeypatch.setattr(
        "almonium_book_processor.catalog.views.translate_edition_inline.delay", unexpected
    )
    response = client.post(reverse("catalog:retry-edition", args=[target.id]))
    assert response.status_code == 302
    run.refresh_from_db()
    assert run.status == "queued"


def test_adaptation_panel_is_collapsible_and_absent_from_the_generated_edition(client, source):
    client.force_login(get_user_model().objects.create_user(username="staff", is_staff=True))
    target = queue_book(source.id).edition
    source_page = client.get(reverse("catalog:edition-detail", args=[source.id]))
    body = source_page.content.decode()
    assert '<details class="panel collapsible-panel adaptation-panel">' in body
    assert "Generate B2 pilot (paid)" in body
    assert "Generate / resume B2 edition (paid)" in body
    # The generated book must not offer to adapt itself again.
    target_page = client.get(reverse("catalog:edition-detail", args=[target.id]))
    body = target_page.content.decode()
    assert "adaptation-panel" not in body
    assert "Generate B2 pilot" not in body
    assert "B2 adaptation — " in body


def test_b1_and_b2_are_siblings_with_distinct_generation_identities(source):
    from almonium_book_processor.catalog.adaptation_quality import adaptation_target

    b1 = queue_book(source.id, target_level="B1")
    b2 = queue_book(source.id, target_level="B2")
    assert b1.id != b2.id and b1.edition_id != b2.edition_id
    assert b1.edition.source_edition_id == b2.edition.source_edition_id == source.id
    assert adaptation_target(b1.edition) == "B1"
    assert adaptation_target(b2.edition) == "B2"


def test_book_rejects_unsupported_level_before_creating_edition(source):
    with pytest.raises(ValueError, match="B1 or B2"):
        queue_book(source.id, target_level="A2")
    assert not source.derived_editions.exists()


def test_b1_failed_staff_retry_preserves_target(client, source):
    run = queue_book(source.id, target_level="B1")
    with pytest.raises(ValueError):
        run_book(run.id, provider=Provider(fail=1))
    client.force_login(get_user_model().objects.create_user("b1retry", is_staff=True))
    response = client.post(reverse("catalog:retry-edition", args=[run.edition_id]))
    assert response.status_code == 302
    run.refresh_from_db()
    assert run.status == "queued" and run.summary["target_level"] == "B1"
    assert source.derived_editions.count() == 1
