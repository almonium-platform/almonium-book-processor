from __future__ import annotations

import json
from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from almonium_book_processor.catalog.chapter_analysis import (
    AnalysisBusy,
    StaleAnalysis,
    analysis_context,
    analysis_spec,
    analyze_chapters,
    queue_analysis,
    snapshot,
)
from almonium_book_processor.catalog.models import AIRun, Chapter, ContentBlock, Edition, Work
from almonium_book_processor.catalog.purge import purge_edition

pytestmark = pytest.mark.django_db


@pytest.fixture
def edition(settings, monkeypatch):
    settings.OPENAI_API_KEY = "fake-key"
    settings.OPENAI_TRANSLATION_DRAFT_MODEL = "test-analysis-model"
    monkeypatch.setattr(
        "almonium_book_processor.catalog.tasks.analyze_edition_chapters.delay", lambda _: None
    )
    work = Work.objects.create(slug="analysis", title="A book", author="Author")
    edition = Edition.objects.create(
        work=work,
        slug="analysis-en",
        language="en",
        source_sha256="a" * 64,
        cefr_level="C1",
        status=Edition.Status.READY,
    )
    for sequence in (1, 2):
        chapter = Chapter.objects.create(edition=edition, sequence=sequence, title=f"{sequence}")
        ContentBlock.objects.create(
            edition=edition,
            chapter=chapter,
            sequence=1,
            block_id=f"c{sequence}.p1",
            block_type="paragraph",
            text="🙂 Ere dawn, the traveler considered the journey.",
        )
    return edition


def output(data):
    return {
        "cefr_estimate": "B2",
        "confidence": 0.75,
        "archaism_score": 0.3,
        "modernisation_would_help": True,
        "evidence": [
            {
                "block_id": data["blocks"][0]["block_id"],
                "quote": "Ere",
                "dimension": "archaism",
                "explanation": "An obsolete conjunction.",
            }
        ],
        "spoiler_free_description": "A traveler considers a journey.",
        "recap": "The traveler reflects before dawn.",
        "hard_words": [
            {
                "block_id": data["blocks"][0]["block_id"],
                "surface": "Ere",
                "explanation": "Before.",
            }
        ],
        "themes": ["Travel"],
        "characters": ["The traveler"],
        "setting": "Before dawn",
        "content_flags": [],
    }


class Provider:
    def __init__(self, hook=None):
        self.calls = []
        self.hook = hook

    def respond(self, body):
        self.calls.append(body)
        data = json.loads(body["input"])
        result = output(data)
        response = {
            "id": f"response-{len(self.calls)}",
            "status": "completed",
            "output": [
                {
                    "type": "message",
                    "content": [
                        {
                            "type": "output_text",
                            "text": json.dumps(result),
                        }
                    ],
                }
            ],
            "usage": {
                "input_tokens": 1000,
                "input_tokens_details": {"cached_tokens": 100},
                "output_tokens": 100,
                "output_tokens_details": {"reasoning_tokens": 20},
            },
        }
        if self.hook:
            self.hook(response, data)
        return response


def test_full_analysis_is_versioned_reusable_and_does_not_change_editorial_level(edition):
    run = queue_analysis(str(edition.id))
    provider = Provider()
    analyze_chapters(str(run.id), provider=provider)
    analyze_chapters(str(run.id), provider=provider)
    assert queue_analysis(str(edition.id)).id == run.id
    run.refresh_from_db()
    edition.refresh_from_db()
    assert len(provider.calls) == 2
    assert run.status == "succeeded"
    assert run.progress == 100
    assert run.summary["completed_windows"] == 2
    assert edition.cefr_level == "C1"
    assert edition.status == "ready"
    assert not edition.artifacts.exists()  # Projections belong to P1-2.
    ai = run.ai_runs.first()
    assert ai.estimated_cost_usd == Decimal("0.000302")
    assert ai.provider_request_id.startswith("response-")
    assert ai.reasoning_tokens == 20
    assert ai.response_payload["evidence_spans"][0]["start"] == 2  # Unicode, not UTF-16.
    body = provider.calls[0]
    assert body["max_output_tokens"] == 4096
    assert body["store"] is False
    assert "untrusted data" in body["instructions"]
    assert list(analysis_context(edition)["chapter_analysis_results"])


def test_retry_reuses_success_and_keeps_failed_response_cost(edition):
    run = queue_analysis(str(edition.id))

    def fail_second(response, data):
        if data["chapter_sequence"] == 2:
            response["output"][0]["content"][0]["text"] = "invalid json"

    with pytest.raises(ValueError):
        analyze_chapters(str(run.id), provider=Provider(fail_second))
    run.refresh_from_db()
    assert run.status == "failed"
    assert run.summary["completed_windows"] == 1
    failed = run.ai_runs.get(status="failed")
    assert failed.estimated_cost_usd == Decimal("0.000302")
    retry = Provider()
    analyze_chapters(str(run.id), provider=retry)
    assert len(retry.calls) == 1
    assert run.ai_runs.count() == 3
    failed.refresh_from_db()
    assert failed.status == "failed"
    assert failed.estimated_cost_usd == Decimal("0.000302")


@pytest.mark.parametrize("failure", ["evidence", "incomplete", "refusal", "confidence", "flags"])
def test_invalid_outputs_are_rejected_but_usage_survives(edition, failure):
    run = queue_analysis(str(edition.id))

    def corrupt(response, data):
        value = output(data)
        if failure == "evidence":
            value["evidence"][0]["quote"] = "Invented text"
        elif failure == "incomplete":
            response["status"] = "incomplete"
        elif failure == "refusal":
            response["output"] = []
            return
        elif failure == "confidence":
            value["confidence"] = 1.2
        elif failure == "flags":
            value["content_flags"] = ["Violence"]
        response["output"][0]["content"][0]["text"] = json.dumps(value)

    with pytest.raises(ValueError):
        analyze_chapters(str(run.id), provider=Provider(corrupt))
    assert run.ai_runs.get().estimated_cost_usd > 0
    assert run.ai_runs.get().status == "failed"
    edition.refresh_from_db()
    assert edition.status == "ready"


def test_long_chapter_windows_cover_every_block_once(edition):
    chapter = edition.chapters.first()
    for sequence in (2, 3, 4):
        ContentBlock.objects.create(
            edition=edition,
            chapter=chapter,
            sequence=sequence,
            block_id=f"c1.p{sequence}",
            block_type="paragraph",
            text="Ere " * 3000,
        )
    plan = snapshot(edition, analysis_spec())
    windows = [w["data"] for w in plan["windows"] if w["data"]["chapter_sequence"] == 1]
    assert len(windows) == 3
    assert all(w["partial"] and w["window_count"] == 3 for w in windows)
    assert [b["block_id"] for w in windows for b in w["blocks"]] == [
        "c1.p1",
        "c1.p2",
        "c1.p3",
        "c1.p4",
    ]
    assert all(len(json.dumps(w, ensure_ascii=False).encode()) < 32000 for w in windows)


def test_oversized_block_fails_before_queueing_without_truncation(edition):
    edition.blocks.filter(block_id="c1.p1").update(text="界" * 9000)
    with pytest.raises(ValueError, match="No text was truncated"):
        queue_analysis(str(edition.id))
    assert not edition.pipeline_runs.exists()
    assert not edition.ai_runs.exists()


def test_window_budget_rejects_whole_plan(edition, monkeypatch):
    monkeypatch.setattr("almonium_book_processor.catalog.chapter_analysis.MAX_WINDOWS", 1)
    with pytest.raises(ValueError, match="limited to 1 windows"):
        queue_analysis(str(edition.id))


def test_edit_before_worker_rejects_stale_job_without_provider_call(edition):
    run = queue_analysis(str(edition.id))
    edition.blocks.filter(block_id="c1.p1").update(text="A replacement.")
    provider = Provider()
    with pytest.raises(StaleAnalysis):
        analyze_chapters(str(run.id), provider=provider)
    assert not provider.calls
    run.refresh_from_db()
    assert run.status == "cancelled"


def test_edit_during_response_records_cost_and_rejects_result(edition):
    run = queue_analysis(str(edition.id))

    def edit(response, data):
        edition.blocks.filter(block_id="c1.p1").update(text="A replacement.")

    with pytest.raises(StaleAnalysis):
        analyze_chapters(str(run.id), provider=Provider(edit))
    assert run.ai_runs.get().estimated_cost_usd > 0
    assert not run.ai_runs.get().response_payload
    assert analysis_context(edition)["chapter_analysis_stale"]


def test_new_revision_reuses_only_unchanged_chapters(edition):
    first = queue_analysis(str(edition.id))
    analyze_chapters(str(first.id), provider=Provider())
    edition.blocks.filter(block_id="c2.p1").update(text="Ere dawn, a different journey began.")
    second = queue_analysis(str(edition.id))
    assert first.id != second.id
    provider = Provider()
    analyze_chapters(str(second.id), provider=provider)
    assert len(provider.calls) == 1
    assert json.loads(provider.calls[0]["input"])["chapter_sequence"] == 2
    second.refresh_from_db()
    assert len(second.summary["results"]) == 2


def test_model_change_does_not_rewrite_history(edition, settings):
    first = queue_analysis(str(edition.id))
    analyze_chapters(str(first.id), provider=Provider())
    previous = first.ai_runs.first()
    settings.OPENAI_TRANSLATION_DRAFT_MODEL = "another-model"
    assert analysis_context(edition)["chapter_analysis_stale"]
    second = queue_analysis(str(edition.id))
    analyze_chapters(str(second.id), provider=Provider())
    previous.model_configuration.refresh_from_db()
    assert previous.model_configuration.model == "test-analysis-model"
    assert second.ai_runs.count() == 2


def test_reverting_text_shows_matching_older_result_without_repaying(edition):
    block = edition.blocks.get(block_id="c2.p1")
    original = block.text
    first = queue_analysis(str(edition.id))
    analyze_chapters(str(first.id), provider=Provider())
    block.text = "Ere dawn, a new journey began."
    block.save()
    second = queue_analysis(str(edition.id))
    analyze_chapters(str(second.id), provider=Provider())
    block.text = original
    block.save()
    assert queue_analysis(str(edition.id)).id == first.id
    context = analysis_context(edition)
    assert context["chapter_analysis_run"].id == first.id
    assert not context["chapter_analysis_stale"]
    assert len(context["chapter_analysis_results"]) == 2


def test_concurrent_delivery_does_not_make_duplicate_paid_calls(edition):
    run = queue_analysis(str(edition.id))
    duplicate = Provider()

    def reenter(response, data):
        with pytest.raises(AnalysisBusy):
            analyze_chapters(str(run.id), provider=duplicate)

    analyze_chapters(str(run.id), provider=Provider(reenter))
    assert not duplicate.calls
    assert run.ai_runs.count() == 2


def test_expired_lease_resumes_completed_windows(edition):
    run = queue_analysis(str(edition.id))
    run.status = "running"
    run.save()
    type(run).objects.filter(id=run.id).update(updated_at=timezone.now() - timedelta(minutes=11))
    analyze_chapters(str(run.id), provider=Provider())
    run.refresh_from_db()
    assert run.status == "succeeded"


def test_purge_during_provider_response_preserves_spend_without_resurrecting_text(edition):
    run = queue_analysis(str(edition.id))

    def remove(response, data):
        purge_edition(edition, reason="operator")

    with pytest.raises(StaleAnalysis):
        analyze_chapters(str(run.id), provider=Provider(remove))
    ai = AIRun.objects.get()
    assert ai.tombstone_id is not None
    assert ai.edition_id is None
    assert ai.estimated_cost_usd > 0
    assert ai.request_payload == ai.response_payload == {}
    assert not Edition.objects.filter(id=edition.id).exists()


def test_transport_error_keeps_unknown_usage_and_allows_explicit_retry(edition):
    run = queue_analysis(str(edition.id))

    def fail(_):
        raise TimeoutError("No response")

    with pytest.raises(ValueError, match="TimeoutError"):
        analyze_chapters(str(run.id), provider=SimpleNamespace(respond=fail))
    assert run.ai_runs.get().estimated_cost_usd is None
    analyze_chapters(str(run.id), provider=Provider())
    assert run.ai_runs.count() == 3


def test_staff_action_requires_post_and_queues_after_commit(
    edition,
    monkeypatch,
    django_capture_on_commit_callbacks,
):
    client = Client()
    url = reverse("catalog:queue-chapter-analysis", args=[edition.id])
    assert client.post(url).status_code == 302
    assert not edition.pipeline_runs.exists()
    user = get_user_model().objects.create_user(username="analyst", is_staff=True)
    client.force_login(user)
    assert client.get(url).status_code == 405
    calls = []
    monkeypatch.setattr(
        "almonium_book_processor.catalog.tasks.analyze_edition_chapters.delay", calls.append
    )
    with django_capture_on_commit_callbacks(execute=True):
        assert client.post(url).status_code == 302
        assert calls == []
    assert calls == [str(edition.pipeline_runs.get().id)]
    page = client.get(reverse("catalog:edition-detail", args=[edition.id]))
    assert "0 / 2 windows completed" in page.content.decode()


def test_private_import_cannot_be_queued_even_by_staff(edition):
    edition.work.visibility = Work.Visibility.PRIVATE
    edition.work.save()
    with pytest.raises(ValueError, match="only for public"):
        queue_analysis(str(edition.id))
    client = Client()
    client.force_login(get_user_model().objects.create_user(username="staff", is_staff=True))
    response = client.post(reverse("catalog:queue-chapter-analysis", args=[edition.id]))
    assert response.status_code == 302
    assert not edition.pipeline_runs.exists()


def test_missing_credentials_fails_before_queue(edition, settings):
    settings.OPENAI_API_KEY = ""
    with pytest.raises(ValueError, match="No OpenAI key"):
        queue_analysis(str(edition.id))
    assert not edition.pipeline_runs.exists()


@pytest.mark.parametrize(
    "field", ["language", "source_sha256", "chapter_sequence", "chapter_title"]
)
def test_source_and_metadata_changes_invalidate_snapshot(edition, field):
    spec = analysis_spec()
    before = snapshot(edition, spec)["hash"]
    if field == "chapter_sequence":
        edition.chapters.filter(sequence=2).update(sequence=3)
    elif field == "chapter_title":
        edition.chapters.filter(sequence=2).update(title="A new title")
    else:
        setattr(edition, field, "de" if field == "language" else "b" * 64)
    assert snapshot(edition, spec)["hash"] != before


def test_queued_request_keeps_model_snapshot(edition, settings):
    run = queue_analysis(str(edition.id))
    settings.OPENAI_TRANSLATION_DRAFT_MODEL = "changed-after-queue"
    provider = Provider()
    analyze_chapters(str(run.id), provider=provider)
    assert all(c["model"] == "test-analysis-model" for c in provider.calls)


def test_stale_results_are_hidden_on_staff_page(edition):
    run = queue_analysis(str(edition.id))
    analyze_chapters(str(run.id), provider=Provider())
    client = Client()
    client.force_login(get_user_model().objects.create_user(username="reviewer", is_staff=True))
    url = reverse("catalog:edition-detail", args=[edition.id])
    content = client.get(url).content.decode()
    assert "estimated B2" in content
    assert "Show recap (spoilers)" in content
    edition.blocks.filter(block_id="c1.p1").update(text="Different text")
    content = client.get(url).content.decode()
    assert "Stale" in content
    assert "estimated B2" not in content


def test_non_staff_cannot_queue_paid_work(edition):
    client = Client()
    client.force_login(get_user_model().objects.create_user(username="reader"))
    assert (
        client.post(reverse("catalog:queue-chapter-analysis", args=[edition.id])).status_code == 302
    )
    assert not edition.pipeline_runs.exists()


def test_chapter_analysis_provider_disables_hidden_retries(monkeypatch):
    from almonium_book_processor.ai.chapter_analysis import OpenAIChapterAnalysisProvider

    options = {}

    def configure(**kwargs):
        options.update(kwargs)
        return "configured-client"

    def init(self):
        self.client = SimpleNamespace(with_options=configure)

    monkeypatch.setattr(
        "almonium_book_processor.ai.openai_provider.OpenAIBatchProvider.__init__", init
    )
    provider = OpenAIChapterAnalysisProvider()
    assert options == {"timeout": 120.0, "max_retries": 0}
    assert provider.client == "configured-client"


def test_broker_failure_is_visible_and_same_job_can_be_requeued(
    edition,
    monkeypatch,
    django_capture_on_commit_callbacks,
):
    def unavailable(_):
        raise ConnectionError("queue unavailable")

    monkeypatch.setattr(
        "almonium_book_processor.catalog.tasks.analyze_edition_chapters.delay", unavailable
    )
    with (
        pytest.raises(ValueError, match="job queue"),
        django_capture_on_commit_callbacks(execute=True),
    ):
        run = queue_analysis(str(edition.id))
    run.refresh_from_db()
    assert run.status == "failed"
    calls = []
    monkeypatch.setattr(
        "almonium_book_processor.catalog.tasks.analyze_edition_chapters.delay", calls.append
    )
    with django_capture_on_commit_callbacks(execute=True):
        retry = queue_analysis(str(edition.id))
    assert retry.id == run.id
    assert retry.status == "queued"
    assert calls == [str(run.id)]
