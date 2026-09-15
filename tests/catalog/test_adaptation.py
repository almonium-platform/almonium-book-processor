import json

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from almonium_book_processor.catalog.adaptation import (
    PROMPT_NAME,
    pilot_context,
    queue_pilot,
    run_pilot,
    word_diff,
)
from almonium_book_processor.catalog.models import (
    AIRun,
    Chapter,
    ContentBlock,
    Edition,
    PromptTemplate,
    Work,
)
from almonium_book_processor.catalog.purge import purge_edition

pytestmark = pytest.mark.django_db


def test_pilot_blind_assessment_is_cached_and_displayed(chapter):
    from almonium_book_processor.catalog.pilot_difficulty import assess_pilot

    run = queue_pilot(chapter.edition_id, chapter.id, dispatch=False)
    run_pilot(run.id, provider=Provider())

    class Judge:
        calls = 0

        def respond(self, body):
            self.calls += 1
            data = json.loads(body["input"])
            assert "target_level" not in data
            assert "author" not in data
            assert "Before dawn, he left." in str(data)
            result = {
                "cefr_estimate": "B1",
                "confidence": 0.7,
                "archaism_score": 0.0,
                "modernisation_would_help": False,
                "evidence": [
                    {
                        "block_id": "b1",
                        "quote": "Before dawn",
                        "dimension": "syntax",
                        "explanation": "Direct narration.",
                    }
                ],
                "spoiler_free_description": "A departure.",
                "recap": "He leaves.",
                "hard_words": [],
                "themes": [],
                "characters": [],
                "setting": "",
                "content_flags": [],
            }
            return {
                "status": "completed",
                "usage": {"input_tokens": 100, "output_tokens": 100},
                "output": [
                    {
                        "type": "message",
                        "content": [{"type": "output_text", "text": json.dumps(result)}],
                    }
                ],
            }

    judge = Judge()
    result = assess_pilot(run.id, provider=judge)
    assert result["cefr_estimate"] == "B1"
    assert assess_pilot(run.id, provider=judge) == result
    assert judge.calls == 1
    run.refresh_from_db()
    assert run.summary["difficulty_check"] == result
    assert pilot_context(run)["rows"]
    chapter.blocks.filter(block_id="b1").update(text="Changed.")
    with pytest.raises(ValueError, match="source changed"):
        assess_pilot(run.id, provider=judge)


def test_editorial_feedback_is_versioned_without_mutating_source(chapter):
    first = queue_pilot(chapter.edition_id, chapter.id, dispatch=False)
    revised = queue_pilot(
        chapter.edition_id, chapter.id, dispatch=False, editorial_feedback="Keep uncertainty."
    )
    assert first.id != revised.id
    assert (
        queue_pilot(
            chapter.edition_id, chapter.id, dispatch=False, editorial_feedback="Keep uncertainty."
        ).id
        == revised.id
    )
    assert (
        first.ai_runs.get().request_payload["source"]
        == revised.ai_runs.get().request_payload["source"]
    )
    assert "Keep uncertainty." in revised.ai_runs.get().request_payload["body"]["instructions"]
    run_pilot(revised.id, provider=Provider())
    assert pilot_context(revised)["stale"] is False
    with pytest.raises(ValueError, match="4,000"):
        queue_pilot(chapter.edition_id, chapter.id, dispatch=False, editorial_feedback="x" * 4001)


@pytest.fixture
def chapter(settings, monkeypatch):
    settings.OPENAI_API_KEY = "fake"
    settings.OPENAI_TRANSLATION_QUALITY_MODEL = "test-model"
    monkeypatch.setattr(
        "almonium_book_processor.catalog.tasks.adapt_chapter_pilot.delay", lambda _: None
    )
    work = Work.objects.create(slug="pilot", title="A book")
    edition = Edition.objects.create(
        work=work, slug="pilot-en", language="en", cefr_level="C1", status="ready"
    )
    chapter = Chapter.objects.create(edition=edition, sequence=1, title="Chapter I")
    for sequence, text in enumerate(["Chapter I", "Ere dawn, he departed.", "He was afraid."]):
        ContentBlock.objects.create(
            edition=edition,
            chapter=chapter,
            sequence=sequence,
            block_id=f"b{sequence}",
            block_type="heading" if sequence == 0 else "paragraph",
            text=text,
        )
    return chapter


class Provider:
    def __init__(self, hook=None):
        self.calls = 0
        self.hook = hook

    def respond(self, body):
        self.calls += 1
        source = json.loads(body["input"])
        blocks = [
            {"block_id": b["block_id"], "text": b["text"], "decision": "kept", "reason": ""}
            for b in source["blocks"]
        ]
        blocks[1].update(
            text="Before dawn, he left.", decision="adapted", reason="Simpler vocabulary."
        )
        response = {
            "id": "test-response",
            "status": "completed",
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
            "usage": {"input_tokens": 1000, "output_tokens": 100},
        }
        if self.hook:
            self.hook(response)
        return response


def test_pilot_preserves_original_and_reuses_success(chapter):
    original = list(chapter.blocks.values_list("text", flat=True))
    run = queue_pilot(chapter.edition_id, chapter.id)
    provider = Provider()
    run_pilot(run.id, provider=provider)
    run_pilot(run.id, provider=provider)
    assert queue_pilot(chapter.edition_id, chapter.id).id == run.id
    run.refresh_from_db()
    chapter.edition.refresh_from_db()
    assert provider.calls == 1
    assert run.status == "succeeded"
    assert run.summary["kept"] == 2
    assert list(chapter.blocks.values_list("text", flat=True)) == original
    assert chapter.edition.cefr_level == "C1"
    assert chapter.edition.status == "ready"
    assert Edition.objects.count() == 1
    assert len(pilot_context(run)["rows"]) == 3
    assert not pilot_context(run)["stale"]
    assert run.ai_runs.get().estimated_cost_usd > 0


@pytest.mark.parametrize("failure", ["missing", "heading", "incomplete"])
def test_invalid_outputs_keep_spend_and_retry_as_new_attempt(chapter, failure):
    run = queue_pilot(chapter.edition_id, chapter.id)

    def corrupt(response):
        content = response["output"][0]["content"][0]
        data = json.loads(content["text"])
        if failure == "missing":
            data["blocks"].pop()
        elif failure == "heading":
            data["blocks"][0].update(text="Another title", decision="adapted", reason="Change")
        else:
            response["status"] = "incomplete"
        content["text"] = json.dumps(data)

    with pytest.raises(ValueError):
        run_pilot(run.id, provider=Provider(corrupt))
    failed = run.ai_runs.get()
    assert failed.status == "failed"
    assert failed.estimated_cost_usd > 0
    assert "adaptation" not in failed.response_payload
    assert queue_pilot(chapter.edition_id, chapter.id).id == run.id
    run_pilot(run.id, provider=Provider())
    assert run.ai_runs.count() == 2
    failed.refresh_from_db()
    assert failed.status == "failed"


def test_decision_metadata_is_corrected_without_discarding_text(chapter):
    run = queue_pilot(chapter.edition_id, chapter.id)

    def wrong_label(response):
        content = response["output"][0]["content"][0]
        data = json.loads(content["text"])
        data["blocks"][1].update(decision="kept", reason="")
        content["text"] = json.dumps(data)

    run_pilot(run.id, provider=Provider(wrong_label))
    ai = run.ai_runs.get()
    assert ai.response_payload["adaptation"]["blocks"][1]["decision"] == "adapted"
    assert len(ai.response_payload["warnings"]) == 2
    cost = ai.estimated_cost_usd
    # Simulate an older validator rejecting this same saved, paid response.
    ai.status = "failed"
    ai.response_payload.pop("adaptation")
    ai.save()
    run.status = "failed"
    run.save()
    assert queue_pilot(chapter.edition_id, chapter.id).id == run.id
    provider = Provider()
    run_pilot(run.id, provider=provider)
    ai.refresh_from_db()
    assert provider.calls == 0
    assert ai.status == "succeeded"
    assert ai.estimated_cost_usd == cost
    assert run.ai_runs.count() == 1


def test_edits_reject_stale_paid_result(chapter):
    run = queue_pilot(chapter.edition_id, chapter.id)

    def edit(_):
        chapter.blocks.filter(block_id="b2").update(text="He was terrified.")

    with pytest.raises(ValueError, match="Source changed"):
        run_pilot(run.id, provider=Provider(edit))
    assert run.ai_runs.get().estimated_cost_usd > 0
    assert pilot_context(run)["stale"]
    assert queue_pilot(chapter.edition_id, chapter.id).id != run.id


def test_purge_during_call_keeps_cost_but_never_restores_text(chapter):
    run = queue_pilot(chapter.edition_id, chapter.id)
    ai_id = run.ai_runs.get().id

    def remove(_):
        purge_edition(chapter.edition, reason="mistake")

    with pytest.raises(ValueError, match="removed"):
        run_pilot(run.id, provider=Provider(remove))
    ai = AIRun.objects.get(pk=ai_id)
    assert ai.tombstone_id
    assert ai.estimated_cost_usd > 0
    assert ai.request_payload == ai.response_payload == {}


def test_private_and_oversized_sources_rejected(chapter):
    chapter.edition.work.visibility = Work.Visibility.PRIVATE
    chapter.edition.work.save()
    with pytest.raises(ValueError, match="public"):
        queue_pilot(chapter.edition_id, chapter.id)
    chapter.edition.work.visibility = Work.Visibility.PUBLIC
    chapter.edition.work.save()
    chapter.blocks.filter(block_id="b1").update(text="x" * 40001)
    with pytest.raises(ValueError, match="limit"):
        queue_pilot(chapter.edition_id, chapter.id)
    assert AIRun.objects.count() == 0


def test_staff_can_queue_and_view_but_nonstaff_cannot(client, chapter):
    url = reverse("catalog:queue-adaptation-pilot", args=[chapter.edition_id])
    assert client.post(url, {"chapter_id": chapter.id}).status_code == 302
    assert AIRun.objects.count() == 0
    user = get_user_model().objects.create_user(username="editor", is_staff=True)
    client.force_login(user)
    assert client.get(url).status_code == 405
    response = client.post(url, {"chapter_id": chapter.id})
    assert response.status_code == 302
    run = chapter.edition.pipeline_runs.get(stage="adapt")
    run_pilot(run.id, provider=Provider())
    page = client.get(response.url)
    assert page.status_code == 200
    assert b"<ins>Before</ins> dawn, he <ins>left.</ins>" in page.content
    assert b"<del>Ere</del> dawn, he <del>departed.</del>" in page.content
    assert b'<div class="pilot-text">He was afraid.</div>' in page.content
    assert b"not an independently verified" in page.content
    other = Edition.objects.create(work=chapter.edition.work, slug="other")
    assert (
        client.get(reverse("catalog:adaptation-pilot", args=[other.id, run.id])).status_code == 404
    )


def test_review_rows_carry_word_level_diff(chapter):
    run = queue_pilot(chapter.edition_id, chapter.id)
    run_pilot(run.id, provider=Provider())
    rows = pilot_context(run)["rows"]
    assert [s["op"] for s in rows[0]["source_segments"]] == ["equal"]
    deleted = [s["text"] for s in rows[1]["source_segments"] if s["op"] == "delete"]
    inserted = [s["text"] for s in rows[1]["target_segments"] if s["op"] == "insert"]
    assert deleted == ["Ere", "departed."]
    assert inserted == ["Before", "left."]
    assert "".join(s["text"] for s in rows[1]["target_segments"]) == "Before dawn, he left."


def test_word_diff_round_trips_whitespace():
    source, target = word_diff("a  b\nc", "a  c\nd")
    assert "".join(s["text"] for s in source) == "a  b\nc"
    assert "".join(s["text"] for s in target) == "a  c\nd"


def test_punctuation_only_edit_is_flagged(chapter):
    run = queue_pilot(chapter.edition_id, chapter.id)

    def repunctuate(response):
        content = response["output"][0]["content"][0]
        data = json.loads(content["text"])
        data["blocks"][2].update(text="He was afraid!", decision="adapted", reason="Emphasis.")
        content["text"] = json.dumps(data)

    run_pilot(run.id, provider=Provider(repunctuate))
    warnings = run.ai_runs.get().response_payload["warnings"]
    assert any(w.startswith("b2: only punctuation") for w in warnings)


def test_edited_prompt_text_must_bump_version(chapter):
    queue_pilot(chapter.edition_id, chapter.id)
    PromptTemplate.objects.filter(name=PROMPT_NAME).update(system_prompt="edited")
    with pytest.raises(ValueError, match="Bump PROMPT_VERSION"):
        queue_pilot(chapter.edition_id, chapter.id)
