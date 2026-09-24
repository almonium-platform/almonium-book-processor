import json
import re
import uuid
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse
from django.utils.html import escape

from almonium_book_processor.catalog import estimates
from almonium_book_processor.catalog.glosses import (
    add_manual,
    chapter_snapshot,
    public_notes,
    queue_book,
    queue_chapter,
    review,
    run_chapter,
)
from almonium_book_processor.catalog.models import Chapter, ContentBlock, Edition, GlossNote, Work

pytestmark = pytest.mark.django_db


@pytest.fixture
def passage(settings):
    settings.OPENAI_API_KEY = "fake"
    settings.OPENAI_TRANSLATION_QUALITY_MODEL = "fake-gloss-model"
    work = Work.objects.create(slug="gloss-work", title="Old Book", author="Writer")
    edition = Edition.objects.create(
        work=work,
        slug="gloss-work-en",
        title="Old Book",
        author="Writer",
        language="en",
        status=Edition.Status.PUBLISHED,
        source_sha256="a" * 64,
    )
    chapter = Chapter.objects.create(edition=edition, sequence=1, title="One")
    block = ContentBlock.objects.create(
        edition=edition,
        chapter=chapter,
        block_id="c1.p1",
        sequence=1,
        block_type=ContentBlock.BlockType.PARAGRAPH,
        text="The eyry stood above the valley.",
        sentences=[{"start": 0, "end": 32}],
        align_group=uuid.uuid4(),
    )
    return edition, chapter, block


class Provider:
    def respond(self, body):
        assert body["model"] == "fake-gloss-model"
        return {
            "id": "gloss-response",
            "status": "completed",
            "usage": {"input_tokens": 100, "output_tokens": 50},
            "output": [
                {
                    "type": "message",
                    "content": [
                        {
                            "type": "output_text",
                            "text": json.dumps(
                                {
                                    "notes": [
                                        {
                                            "block_id": "c1.p1",
                                            "quote": "eyry",
                                            "body": (
                                                "An eyry is an eagle's high nest, a word that "
                                                "helps preserve the image in this passage."
                                            ),
                                        }
                                    ]
                                }
                            ),
                        }
                    ],
                }
            ],
        }


def test_paid_candidates_need_review_and_follow_exact_source(passage):
    edition, chapter, block = passage
    run = queue_chapter(chapter.id, dispatch=False)
    assert queue_chapter(chapter.id, dispatch=False).id == run.id
    run_chapter(run.id, provider=Provider())
    run.refresh_from_db()
    note = GlossNote.objects.get()
    assert run.status == "succeeded"
    assert run.ai_runs.get().estimated_cost_usd is not None
    assert note.status == GlossNote.Status.DRAFT
    assert public_notes(edition) == {}
    reviewer = get_user_model().objects.create_user("gloss-editor", is_staff=True)
    review(note.id, actor=reviewer, approve=True)
    assert public_notes(edition)["c1.p1"][0]["quote"] == "eyry"
    response = Client().get(f"/api/v1/public/editions/{edition.slug}/blocks/")
    assert response.status_code == 200
    assert response.json()[0]["notes"][0]["body"].startswith("An eyry")
    block.text = "The nest stood above the valley."
    block.save(update_fields=["text"])
    assert public_notes(edition) == {}


def test_manual_gloss_must_be_unique_and_in_one_sentence(passage):
    _, chapter, block = passage
    note = add_manual(chapter, block_id=block.block_id, quote="eyry", body="An eagle's nest.")
    assert note.status == GlossNote.Status.DRAFT
    with pytest.raises(ValueError, match="already has"):
        add_manual(chapter, block_id=block.block_id, quote="eyry", body="Another meaning")
    with pytest.raises(ValueError, match="occur exactly once"):
        add_manual(chapter, block_id=block.block_id, quote="absent", body="A note")


def test_literary_letter_passages_are_included(passage):
    _, chapter, block = passage
    block.block_type = ContentBlock.BlockType.LETTER
    block.save(update_fields=["block_type"])
    assert chapter_snapshot(chapter)["blocks"] == [{"block_id": block.block_id, "text": block.text}]


def test_staff_review_rejects_overlapping_approved_notes(passage):
    edition, chapter, block = passage
    editor = get_user_model().objects.create_user("gloss-reviewer", is_staff=True)
    first = add_manual(chapter, block_id=block.block_id, quote="eyry", body="An eagle's nest.")
    second = add_manual(
        chapter, block_id=block.block_id, quote="The eyry", body="A nest on a height."
    )
    review(first.id, actor=editor, approve=True)
    with pytest.raises(ValueError, match="already covers"):
        review(second.id, actor=editor, approve=True)
    assert len(public_notes(edition)[block.block_id]) == 1


def test_gloss_review_requires_staff_and_approved_content_only(passage):
    edition, chapter, block = passage
    note = add_manual(chapter, block_id=block.block_id, quote="eyry", body="An eagle's nest.")
    url = reverse("catalog:gloss-review", args=[edition.id])
    assert Client().get(url).status_code == 302
    ordinary = get_user_model().objects.create_user("reader")
    client = Client()
    client.force_login(ordinary)
    assert client.get(url).status_code == 302
    editor = get_user_model().objects.create_user("staff", is_staff=True)
    client.force_login(editor)
    assert client.get(url).status_code == 200
    response = client.post(
        reverse("catalog:review-gloss", args=[edition.id, note.id]),
        {"action": "approve", "body": "An eagle's high nest."},
    )
    assert response.status_code == 302
    note.refresh_from_db()
    assert note.body == "An eagle's high nest."
    assert note.status == GlossNote.Status.APPROVED


def test_invalid_paid_output_records_failure_without_publishing(passage):
    _, chapter, _ = passage

    class InvalidProvider(Provider):
        def respond(self, body):
            response = super().respond(body)
            response["output"][0]["content"][0]["text"] = json.dumps(
                {"notes": [{"block_id": "c1.p1", "quote": "missing", "body": "A note."}]}
            )
            return response

    run = queue_chapter(chapter.id, dispatch=False)
    with pytest.raises(ValueError, match="unsupported quote"):
        run_chapter(run.id, provider=InvalidProvider())
    run.refresh_from_db()
    assert run.status == "failed"
    assert run.ai_runs.get().status == "failed"
    assert not GlossNote.objects.exists()


def test_whole_book_queue_skips_generated_and_empty_chapters(passage):
    edition, chapter, block = passage
    run = queue_chapter(chapter.id, dispatch=False)
    run_chapter(run.id, provider=Provider())
    second = Chapter.objects.create(edition=edition, sequence=2, title="Two")
    ContentBlock.objects.create(
        edition=edition,
        chapter=second,
        block_id="c2.p1",
        sequence=2,
        block_type=ContentBlock.BlockType.PARAGRAPH,
        text="A second passage.",
        sentences=[{"start": 0, "end": 17}],
        align_group=uuid.uuid4(),
    )
    Chapter.objects.create(edition=edition, sequence=3, title="Blank")
    assert queue_book(edition, dispatch=False) == {"queued": 1, "generated": 1, "skipped": 1}
    assert queue_book(edition, dispatch=False) == {"queued": 1, "generated": 1, "skipped": 1}
    assert edition.pipeline_runs.filter(stage="glosses").count() == 2
    staff = get_user_model().objects.create_user("book-gloss-staff", is_staff=True)
    client = Client()
    client.force_login(staff)
    response = client.post(
        reverse("catalog:queue-book-glosses", args=[edition.id]),
        {"chapter_id": str(second.id)},
    )
    assert response.status_code == 302
    assert response.url.endswith(f"?chapter={second.id}")
    page = client.get(response.url).content.decode()
    assert "1 in progress. Chapter 1 is already generated" not in page  # nothing left to list
    assert "Every chapter is generated." not in page
    assert "1 in progress." in page
    assert "Generate whole book" not in page  # the only chapter left is already queued


def test_page_prices_what_is_left_and_offers_to_regenerate(passage):
    edition, chapter, block = passage
    run = queue_chapter(chapter.id, dispatch=False)
    run_chapter(run.id, provider=Provider())
    second = Chapter.objects.create(edition=edition, sequence=2, title="Two")
    ContentBlock.objects.create(
        edition=edition,
        chapter=second,
        block_id="c2.p1",
        sequence=2,
        block_type=ContentBlock.BlockType.PARAGRAPH,
        text="A second passage. " * 200,
        sentences=[],
        align_group=uuid.uuid4(),
    )
    staff = get_user_model().objects.create_user("price-staff", is_staff=True)
    client = Client()
    client.force_login(staff)
    url = reverse("catalog:gloss-review", args=[edition.id])
    page = client.get(f"{url}?chapter={chapter.id}").content.decode()
    left = estimates.gloss_book([(second, chapter_snapshot(second))])
    assert 'Generate whole book<span class="cost">' in page
    assert f'<span class="cost-value">{escape(left.label)}</span>' in page
    assert "1 chapter left. Chapter 1 is already generated and won’t be charged again." in page
    # The generated chapter offers to regenerate and shows what its run cost.
    assert "Regenerate" in page and 'name="regenerate"' in page
    assert re.search(r'candidates · <span class="tabular">\$0\.\d+</span>', page)
    response = client.post(
        reverse("catalog:queue-glosses", args=[edition.id]),
        {"chapter_id": str(chapter.id), "regenerate": "1"},
    )
    assert response.status_code == 302
    runs = edition.pipeline_runs.filter(stage="glosses", summary__chapter_id=str(chapter.id))
    assert runs.count() == 2
    assert runs.filter(status="queued").count() == 1
    # Without the flag, a generated chapter is never paid for twice.
    assert queue_chapter(chapter.id, dispatch=False).id == run.id
    assert runs.count() == 2


def test_estimate_labels_confirm_only_above_the_threshold():
    from decimal import Decimal

    from almonium_book_processor.catalog.estimates import Estimate, unavailable

    small = Estimate(Decimal("0.1432"), "note", "Generate 2 chapters")
    assert small.label == "~$0.14" and small.confirm == ""
    large = Estimate(Decimal("4.1"), "note", "Generate 29 chapters")
    assert large.confirm == "Generate 29 chapters for about $4.10?"
    assert Estimate(Decimal("0.004")).label == "<$0.01"
    assert Estimate(Decimal(0)).label == "$0"
    missing = unavailable("no text")
    assert missing.label == "AI" and missing.note.startswith("No estimate available")


def test_cost_tags_render_the_suffix_tooltip_and_question():
    from decimal import Decimal

    from django.template import Context, Template

    from almonium_book_processor.catalog.estimates import Estimate

    html = Template(
        "{% load catalog_extras %}<button{% cost_attrs e %}>Go{% cost e %}</button>"
    ).render(Context({"e": Estimate(Decimal("4.1"), "Four <chapters>", "Generate 4 chapters")}))
    assert 'title="Four &lt;chapters&gt;"' in html
    assert 'data-confirm="Generate 4 chapters for about $4.10?"' in html
    assert '<span class="cost-value">~$4.10</span>' in html


def test_gloss_estimate_prices_each_window_at_the_quality_rate(passage):
    edition, chapter, block = passage
    estimate = estimates.gloss_chapter(chapter)
    # One small window: input tokens of prompt plus text at $2/M, 150 output at $12/M.
    assert Decimal("0.001") < estimate.usd < Decimal("0.005")
    Chapter.objects.create(edition=edition, sequence=9, title="Empty")
    empty = Chapter.objects.get(sequence=9)
    assert estimates.gloss_chapter(empty).usd is None
