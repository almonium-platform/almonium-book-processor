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
from almonium_book_processor.catalog.chapter_projections import (
    percentile,
    refresh_projections,
    set_chapter_role,
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
    monkeypatch.setattr(
        "almonium_book_processor.catalog.tasks.project_chapter_analysis.delay", lambda _: None
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


def test_adaptation_gate_checks_current_windows_not_editorial_label(edition):
    from almonium_book_processor.catalog.adaptation_quality import adaptation_quality
    from almonium_book_processor.catalog.services import complete_review
    from almonium_book_processor.catalog.tasks import publication_blocker

    edition.edition_type = Edition.EditionType.ADAPTATION
    edition.cefr_level = "B2"
    edition.save()
    edition.blocks.update(attributes={"adaptation": {"target_level": "B2"}})
    assert "current difficulty" in adaptation_quality(edition)["adaptation_blocker"]
    run = queue_analysis(str(edition.id))
    analyze_chapters(str(run.id), provider=Provider())
    assert not adaptation_quality(edition)["adaptation_blocker"]
    # Even a minority above-target window must not disappear in a percentile.
    context = analysis_context(edition)
    context["chapter_projections"][1]["difficulty"]["max_level"] = "C1"
    quality = adaptation_quality(edition, context)
    assert quality["adaptation_above_chapters"] == [2]
    assert "not achieved" in quality["adaptation_blocker"]
    edition.blocks.filter(chapter__sequence=2).update(text="Changed text.")
    assert "current difficulty" in publication_blocker(edition)
    edition.status = Edition.Status.REVIEW
    with pytest.raises(ValueError, match="current difficulty"):
        complete_review(edition=edition, reviewer=get_user_model().objects.create_user("gate"))


def test_passing_review_labels_an_adaptation_with_its_target(edition):
    from almonium_book_processor.catalog.forms import EditionMetadataForm
    from almonium_book_processor.catalog.services import complete_review

    edition.edition_type = Edition.EditionType.ADAPTATION
    edition.cefr_level = None
    edition.status = Edition.Status.REVIEW
    edition.save()
    edition.blocks.update(attributes={"adaptation": {"target_level": "B2"}})
    # The form proposes the generation target; the row itself stays unlabelled.
    assert EditionMetadataForm.for_edition(edition).initial["cefr_level"] == "B2"
    assert Edition.objects.get(id=edition.id).cefr_level is None

    client = Client()
    client.force_login(get_user_model().objects.create_user("labeller", is_staff=True))
    response = client.get(reverse("catalog:edition-detail", args=[edition.id]))
    assert b"difficulty gate is not passing" in response.content
    review_url = reverse("catalog:complete-edition-review", args=[edition.id]).encode()
    assert review_url not in response.content

    run = queue_analysis(str(edition.id))
    analyze_chapters(str(run.id), provider=Provider())
    response = client.get(reverse("catalog:edition-detail", args=[edition.id]))
    assert b"labels it B2" in response.content
    assert review_url in response.content
    complete_review(edition=edition, reviewer=get_user_model().objects.create_user("gate-ok"))
    edition.refresh_from_db()
    assert edition.status == Edition.Status.READY
    assert edition.cefr_level == "B2"


def test_passing_review_keeps_an_explicit_editorial_label(edition):
    from almonium_book_processor.catalog.services import complete_review

    edition.edition_type = Edition.EditionType.ADAPTATION
    edition.cefr_level = "B1"
    edition.status = Edition.Status.REVIEW
    edition.save()
    edition.blocks.update(attributes={"adaptation": {"target_level": "B2"}})
    run = queue_analysis(str(edition.id))
    analyze_chapters(str(run.id), provider=Provider())
    complete_review(edition=edition, reviewer=get_user_model().objects.create_user("keeper"))
    edition.refresh_from_db()
    assert edition.cefr_level == "B1"


def test_adaptation_gate_exposes_evidence_and_below_target(edition):
    from almonium_book_processor.catalog.adaptation_quality import adaptation_quality

    edition.edition_type = Edition.EditionType.ADAPTATION
    edition.save()
    edition.blocks.update(attributes={"adaptation": {"target_level": "B2"}})
    run = queue_analysis(str(edition.id))
    analyze_chapters(str(run.id), provider=Provider())
    context = analysis_context(edition)
    context["chapter_projections"][0]["difficulty"].update(cefr_estimate="B1", max_level="B1")
    assert adaptation_quality(edition, context)["adaptation_below_chapters"] == [1]
    client = Client()
    client.force_login(get_user_model().objects.create_user("quality-ui", is_staff=True))
    response = client.get(reverse("catalog:edition-detail", args=[edition.id]))
    assert b"Adaptation target: B2" in response.content
    assert b"judge evidence" in response.content
    assert b"An obsolete conjunction" in response.content


def test_worker_difficulty_warning_cannot_be_dismissed_and_clears_after_reassessment(edition):
    from almonium_book_processor.catalog.adaptation_quality import DIFFICULTY_WARNING
    from almonium_book_processor.catalog.services import resolve_review_warning

    edition.edition_type = Edition.EditionType.ADAPTATION
    edition.save()
    edition.blocks.update(attributes={"adaptation": {"target_level": "B2"}})
    edition.chapters.filter(sequence=2).update(analysis_role=Chapter.AnalysisRole.FRONT)

    def harder_front_matter(response, data):
        if data["chapter_sequence"] == 2:
            content = response["output"][0]["content"][0]
            result = json.loads(content["text"])
            result["cefr_estimate"] = "C1"
            content["text"] = json.dumps(result)

    run = queue_analysis(str(edition.id))
    analyze_chapters(str(run.id), provider=Provider(harder_front_matter))
    warning = edition.warnings.get(code=DIFFICULTY_WARNING)
    assert warning.resolved_at is None
    assert "not achieved" in warning.message
    assert analysis_context(edition)["book_difficulty"]["cefr_estimate"] == "B2"
    with pytest.raises(ValueError, match="not achieved"):
        resolve_review_warning(
            edition=edition,
            warning_id=warning.id,
            reviewer=get_user_model().objects.create_user("cannot-dismiss"),
        )
    edition.blocks.filter(chapter__sequence=2).update(
        text="Ere dawn, the traveler considered a new journey."
    )
    replacement = queue_analysis(str(edition.id))
    analyze_chapters(str(replacement.id), provider=Provider())
    warning.refresh_from_db()
    assert warning.resolved_at is not None
    assert warning.resolved_by is None
    assert edition.warnings.filter(code=DIFFICULTY_WARNING).count() == 1


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
    assert edition.artifacts.filter(is_current=True).count() == 5
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


@pytest.mark.parametrize("failure", ["evidence", "incomplete", "refusal", "confidence"])
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
        response["output"][0]["content"][0]["text"] = json.dumps(value)

    with pytest.raises(ValueError):
        analyze_chapters(str(run.id), provider=Provider(corrupt))
    ai = run.ai_runs.get()
    assert ai.estimated_cost_usd > 0
    assert ai.status == "failed"
    assert ai.error.startswith("Chapter 1 window 1/1: ")
    run.refresh_from_db()
    assert run.error.startswith("Chapter 1 window 1/1: ")
    assert "retry reuses validated windows" in run.error
    if failure == "evidence":
        assert "No cited evidence occurs" in run.error
        assert "Invented" not in run.error
    else:
        # Provider and schema failures stay type-only; they may quote book text.
        assert "did not complete validation" in run.error
    edition.refresh_from_db()
    assert edition.status == "ready"


def test_whitespace_slips_are_repaired_and_unbacked_items_dropped_not_fatal(edition):
    """A sloppy hard word or unevidenced flag must not discard a paid, otherwise valid window."""
    run = queue_analysis(str(edition.id))

    def sloppy(response, data):
        value = output(data)
        block = data["blocks"][0]["block_id"]
        value["evidence"].append(
            {"block_id": block, "quote": "the trav eler", "dimension": "syntax", "explanation": "x"}
        )
        value["hard_words"] = [
            {"block_id": block, "surface": "consid ered", "explanation": "Thought about."},
            {"block_id": block, "surface": "phantasm", "explanation": "Not in the text."},
        ]
        value["content_flags"] = ["Peril"]
        response["output"][0]["content"][0]["text"] = json.dumps(value)

    analyze_chapters(str(run.id), provider=Provider(sloppy))
    ai = run.ai_runs.order_by("created_at").first()
    assert {r.status for r in run.ai_runs.all()} == {"succeeded"}
    analysis = ai.response_payload["analysis"]
    text = edition.chapters.get(sequence=1).blocks.get().text
    assert [e["quote"] for e in analysis["evidence"]] == ["Ere", "the traveler"]
    assert [w["surface"] for w in analysis["hard_words"]] == ["considered"]
    for span in ai.response_payload["evidence_spans"]:
        assert text[span["start"] : span["end"]] in ("Ere", "the traveler", "considered")
    assert analysis["content_flags"] == []
    notes = ai.response_payload["validation_notes"]
    assert any("Dropped hard word" in n for n in notes)
    assert any("Unsupported content flag: Peril" in n for n in notes)
    assert "phantasm" not in json.dumps(analysis)


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


def book_assessment(edition):
    return edition.artifacts.get(kind="difficulty", chapter__isnull=True, is_current=True)


def graded_provider(levels):
    def grade(response, data):
        content = response["output"][0]["content"][0]
        value = json.loads(content["text"])
        value["cefr_estimate"] = levels[data["chapter_sequence"] - 1]
        value["confidence"] = 0.4 if data["chapter_sequence"] == 1 else 0.9
        content["text"] = json.dumps(value)

    return Provider(grade)


def test_nearest_rank_percentile_does_not_interpolate_cefr_bands():
    assert percentile([]) is None
    assert percentile(["B1"]) == "B1"
    assert percentile(["B1", "B2", "C1", "C2"]) == "C1"
    assert percentile(["B1", "B2", "C1", "C2"], [100, 1, 1, 1]) == "B1"


def test_book_distribution_and_weighted_comparison_with_editorial_override(edition):
    for sequence in (3, 4):
        chapter = Chapter.objects.create(edition=edition, sequence=sequence)
        ContentBlock.objects.create(
            edition=edition,
            chapter=chapter,
            block_id=f"c{sequence}.p1",
            sequence=1,
            block_type="paragraph",
            text="Ere dawn, the traveler considered the journey.",
        )
    edition.blocks.filter(block_id="c1.p1").update(text="Ere dawn. " + "word " * 1000)
    run = queue_analysis(str(edition.id))
    analyze_chapters(str(run.id), provider=graded_provider(["B1", "B2", "C1", "C2"]))
    book = book_assessment(edition).payload
    assert book["cefr_estimate"] == "C1"
    assert book["weighted_comparison"] == "B1"
    assert (book["min_level"], book["max_level"]) == ("B1", "C2")
    assert book["distribution"] == {"A1": 0, "A2": 0, "B1": 1, "B2": 1, "C1": 1, "C2": 1}
    assert book["confidence_min"] == 0.4
    assert book["confidence_max"] == 0.9
    assert book["chapters_completed"] == book["chapters_total"] == 4
    edition.refresh_from_db()
    assert edition.cefr_level == "C1"
    assert analysis_context(edition)["projection_state"] == "complete"


def test_front_matter_exclusion_reuses_chapter_artifacts_and_no_provider(edition):
    run = queue_analysis(str(edition.id))
    analyze_chapters(str(run.id), provider=graded_provider(["B1", "C2"]))
    assert book_assessment(edition).payload["cefr_estimate"] == "C2"
    chapter_ids = set(
        edition.artifacts.filter(chapter__isnull=False, is_current=True).values_list(
            "id", flat=True
        )
    )
    set_chapter_role(str(edition.id), str(edition.chapters.get(sequence=2).id), "front")
    assert analysis_context(edition)["projection_state"] == "stale"
    refresh_projections(str(run.id))
    book = book_assessment(edition).payload
    assert book["cefr_estimate"] == "B1"
    assert book["chapters_total"] == book["chapters_completed"] == 1
    assert book["chapters_excluded"] == 1
    assert (
        set(
            edition.artifacts.filter(chapter__isnull=False, is_current=True).values_list(
                "id", flat=True
            )
        )
        == chapter_ids
    )
    assert edition.ai_runs.count() == 2


def test_all_excluded_and_empty_chapters_do_not_invent_a_book_level(edition):
    Chapter.objects.create(edition=edition, sequence=3, title="Empty chapter")
    edition.chapters.update(analysis_role="back")
    run = queue_analysis(str(edition.id))
    analyze_chapters(str(run.id), provider=Provider())
    book = book_assessment(edition).payload
    assert book["cefr_estimate"] is None
    assert book["chapters_total"] == 0
    assert book["chapters_excluded"] == 2
    assert analysis_context(edition)["projection_state"] == "empty"


def test_partial_failed_run_keeps_complete_chapters_and_coverage(edition):
    run = queue_analysis(str(edition.id))

    def fail(response, data):
        if data["chapter_sequence"] == 2:
            response["status"] = "incomplete"

    with pytest.raises(ValueError):
        analyze_chapters(str(run.id), provider=Provider(fail))
    book = book_assessment(edition).payload
    assert book["chapters_completed"] == 1
    assert book["chapters_total"] == 2
    assert not book["complete"]
    assert book["cefr_estimate"] == "B2"
    assert book["whitespace_tokens_analyzed"] < book["whitespace_tokens_total"]
    context = analysis_context(edition)
    assert context["projection_state"] == "failed"
    assert len(context["chapter_projections"]) == 2
    analyze_chapters(str(run.id), provider=Provider())
    assert analysis_context(edition)["projection_state"] == "complete"


def test_partial_chapter_never_counts_as_complete_in_book_percentile(edition):
    chapter = edition.chapters.first()
    for sequence in (2, 3):
        ContentBlock.objects.create(
            edition=edition,
            chapter=chapter,
            block_id=f"c1.p{sequence}",
            sequence=sequence,
            block_type="paragraph",
            text="Ere " * 3000,
        )
    run = queue_analysis(str(edition.id))

    def fail(response, data):
        if data["window"] == 2:
            response["status"] = "incomplete"

    with pytest.raises(ValueError):
        analyze_chapters(str(run.id), provider=Provider(fail))
    book = book_assessment(edition).payload
    assert book["cefr_estimate"] is None
    assert book["chapters_completed"] == 0
    partial = chapter.artifacts.get(kind="difficulty", is_current=True).payload
    assert partial["cefr_estimate"] == "B2"
    assert not partial["complete"]
    assert partial["windows_completed"] == 1
    analyze_chapters(str(run.id), provider=Provider())
    summary = chapter.artifacts.get(kind="chapter_summary", is_current=True).payload
    assert summary["complete"]
    assert [s["window"] for s in summary["sections"]] == [1, 2]


def test_projection_versions_are_independent_and_rebuilds_are_idempotent(edition, monkeypatch):
    run = queue_analysis(str(edition.id))
    analyze_chapters(str(run.id), provider=Provider())
    count = edition.artifacts.count()
    refresh_projections(str(run.id))
    assert edition.artifacts.count() == count
    difficulty_ids = set(
        edition.artifacts.filter(kind="difficulty", is_current=True).values_list("id", flat=True)
    )
    summary_ids = set(
        edition.artifacts.filter(kind="chapter_summary", is_current=True).values_list(
            "id", flat=True
        )
    )
    monkeypatch.setattr(
        "almonium_book_processor.catalog.chapter_projections.SUMMARY_VERSION", "chapter-summary-v2"
    )
    refresh_projections(str(run.id))
    assert (
        set(
            edition.artifacts.filter(kind="difficulty", is_current=True).values_list(
                "id", flat=True
            )
        )
        == difficulty_ids
    )
    assert not summary_ids & set(
        edition.artifacts.filter(kind="chapter_summary", is_current=True).values_list(
            "id", flat=True
        )
    )
    assert edition.ai_runs.count() == 2


def test_completed_pre_projection_run_backfills_without_credentials_or_ai(edition, settings):
    run = queue_analysis(str(edition.id))
    analyze_chapters(str(run.id), provider=Provider())
    edition.artifacts.all().delete()
    settings.OPENAI_API_KEY = ""
    provider = Provider()
    analyze_chapters(str(run.id), provider=provider)
    assert not provider.calls
    assert book_assessment(edition).payload["complete"]


def test_approved_text_edit_invalidates_projection_and_retains_history(edition):
    from almonium_book_processor.catalog.services import revise_block_text

    run = queue_analysis(str(edition.id))
    analyze_chapters(str(run.id), provider=Provider())
    previous_book = book_assessment(edition)
    block = edition.blocks.get(block_id="c1.p1")
    revise_block_text(
        edition=edition,
        block_id=block.id,
        revised_text="Ere dawn, revised prose.",
        editor=get_user_model().objects.create_user(username="projection-editor"),
    )
    previous_book.refresh_from_db()
    assert not previous_book.is_current
    assert analysis_context(edition)["projection_state"] == "stale"
    with pytest.raises(StaleAnalysis):
        refresh_projections(str(run.id))
    assert not edition.artifacts.filter(is_current=True).exists()


def test_missing_chapter_artifact_is_stale_instead_of_a_server_error(edition):
    run = queue_analysis(str(edition.id))
    analyze_chapters(str(run.id), provider=Provider())
    edition.chapters.first().artifacts.filter(kind="difficulty").delete()
    context = analysis_context(edition)
    assert context["projection_state"] == "stale"
    assert context["book_difficulty"] is None


def test_role_is_owner_scoped_and_invalid_choice_is_rejected(edition):
    other = Edition.objects.create(work=edition.work, slug="other-edition")
    foreign = Chapter.objects.create(edition=other, sequence=1)
    with pytest.raises(ValueError, match="does not belong"):
        set_chapter_role(str(edition.id), str(foreign.id), "front")
    with pytest.raises(ValueError, match="valid chapter role"):
        set_chapter_role(str(edition.id), str(edition.chapters.first().id), "invalid")


def test_staff_can_queue_free_refresh_and_edit_chapter_role(
    edition,
    settings,
    monkeypatch,
    django_capture_on_commit_callbacks,
):
    run = queue_analysis(str(edition.id))
    analyze_chapters(str(run.id), provider=Provider())
    settings.OPENAI_API_KEY = ""
    client = Client()
    url = reverse("catalog:refresh-chapter-projections", args=[edition.id])
    assert client.post(url).status_code == 302
    client.force_login(
        get_user_model().objects.create_user(username="projection-staff", is_staff=True)
    )
    assert client.get(url).status_code == 405
    calls = []
    monkeypatch.setattr(
        "almonium_book_processor.catalog.tasks.project_chapter_analysis.delay", calls.append
    )
    with django_capture_on_commit_callbacks(execute=True):
        assert client.post(url).status_code == 302
    assert calls == [str(run.id)]
    chapter = edition.chapters.first()
    role_url = reverse("catalog:update-chapter-role", args=[edition.id, chapter.id])
    assert client.get(role_url).status_code == 405
    assert client.post(role_url, {"analysis_role": "front"}).status_code == 302
    chapter.refresh_from_db()
    assert chapter.analysis_role == "front"
    content = client.get(reverse("catalog:edition-detail", args=[edition.id])).content.decode()
    assert "Previous assessments are stale" in content


def test_late_old_model_job_cannot_replace_current_projections(edition, settings):
    old = queue_analysis(str(edition.id))
    settings.OPENAI_TRANSLATION_DRAFT_MODEL = "new-analysis-model"
    current = queue_analysis(str(edition.id))
    analyze_chapters(str(current.id), provider=graded_provider(["C1", "C2"]))
    artifact = book_assessment(edition)
    analyze_chapters(str(old.id), provider=graded_provider(["B1", "B1"]))
    assert book_assessment(edition).id == artifact.id
    assert analysis_context(edition)["book_difficulty"]["cefr_estimate"] == "C2"


def test_projection_version_change_is_stale_until_free_rebuild(edition, monkeypatch):
    run = queue_analysis(str(edition.id))
    analyze_chapters(str(run.id), provider=Provider())
    monkeypatch.setattr(
        "almonium_book_processor.catalog.chapter_projections.DIFFICULTY_VERSION",
        "chapter-difficulty-v2",
    )
    assert analysis_context(edition)["projection_state"] == "stale"
    refresh_projections(str(run.id))
    assert analysis_context(edition)["projection_state"] == "complete"
    assert edition.ai_runs.count() == 2


def test_language_edit_invalidates_persisted_projections(edition):
    from almonium_book_processor.catalog.metadata import confirm_metadata

    run = queue_analysis(str(edition.id))
    analyze_chapters(str(run.id), provider=Provider())
    confirm_metadata(edition, language="de")
    assert not edition.artifacts.filter(is_current=True).exists()
    assert analysis_context(edition)["projection_state"] == "stale"


def test_projection_broker_failure_is_reported_without_changing_analysis(
    edition,
    monkeypatch,
    django_capture_on_commit_callbacks,
):
    from almonium_book_processor.catalog.chapter_projections import queue_projection_refresh

    run = queue_analysis(str(edition.id))
    analyze_chapters(str(run.id), provider=Provider())

    def unavailable(_):
        raise ConnectionError("broker unavailable")

    monkeypatch.setattr(
        "almonium_book_processor.catalog.tasks.project_chapter_analysis.delay",
        unavailable,
    )
    with (
        pytest.raises(ValueError, match="Could not queue the projection"),
        django_capture_on_commit_callbacks(execute=True),
    ):
        queue_projection_refresh(str(edition.id))
    run.refresh_from_db()
    assert run.status == "succeeded"
    assert book_assessment(edition).payload["complete"]


def test_non_english_contract_is_versioned_without_invalidating_english():
    english = analysis_spec("en")
    ukrainian = analysis_spec("uk")
    assert english["prompt_version"] == 3
    assert ukrainian["prompt_version"] == 4
    assert "input language code" in ukrainian["system_prompt"]
    assert "summaries in English" not in ukrainian["system_prompt"]


def test_wrong_language_is_rejected_after_recording_cost(edition):
    edition.language = "uk"
    edition.save(update_fields=["language"])
    run = queue_analysis(str(edition.id))
    with pytest.raises(ValueError):
        analyze_chapters(str(run.id), provider=Provider())
    ai = AIRun.objects.get(pipeline_run=run)
    assert ai.status == AIRun.Status.FAILED
    assert ai.estimated_cost_usd > 0
    assert "analysis" not in ai.response_payload
