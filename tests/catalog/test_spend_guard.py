"""The spend guard reads the ledger for money paid twice and says so in numbers."""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from almonium_book_processor.catalog.models import (
    AIRun,
    Edition,
    EditionTombstone,
    ModelConfiguration,
    PipelineRun,
    PromptTemplate,
    Work,
)
from almonium_book_processor.catalog.spend_guard import guard_report, latest_report, record_report

pytestmark = pytest.mark.django_db


@pytest.fixture
def ledger():
    work = Work.objects.create(slug="w", title="A book", author="Author")
    source = Edition.objects.create(work=work, slug="w-en", language="en", status="ready")
    configuration = ModelConfiguration.objects.create(
        name="judge", provider="openai", model="gpt", purpose="judge"
    )
    prompt = PromptTemplate.objects.create(
        name="judge", version=1, purpose="judge", system_prompt="x", user_template="y"
    )
    run = PipelineRun.objects.create(
        edition=source,
        stage=PipelineRun.Stage.ADAPT,
        processor_version="adaptation-wording-v1",
        input_hash="",
        idempotency_key="run",
    )

    def call(payload, *, input_hash, status="succeeded", cost="0.10"):
        return AIRun.objects.create(
            edition=source,
            pipeline_run=run,
            model_configuration=configuration,
            prompt_template=prompt,
            input_hash=input_hash,
            idempotency_key=uuid.uuid4().hex,
            status=status,
            estimated_cost_usd=Decimal(cost),
            request_payload=payload,
        )

    return source, call


def test_the_same_request_paid_again_is_counted_and_a_deliberate_rereading_is_not(ledger):
    source, call = ledger
    window = {"window": {"blocks": [{"text": "Once upon a time."}]}}
    call(window, input_hash="h1")
    call(window, input_hash="h1")  # the same ask, paid again
    call(window, input_hash="h1-reading-2")  # a judge's second reading of a disputed chapter
    other = {"window": {"blocks": [{"text": "Something else."}]}}
    call(other, input_hash="h2")
    for _ in range(3):
        call({"window": {"blocks": [{"text": "A title page."}]}}, input_hash="h3", status="failed")

    from datetime import timedelta

    from django.utils import timezone

    retried = call(
        {"window": {"blocks": [{"text": "Retried once."}]}}, input_hash="h4", status="failed"
    )
    AIRun.objects.filter(pk=retried.pk).update(created_at=timezone.now() - timedelta(minutes=1))
    call({"window": {"blocks": [{"text": "Retried once."}]}}, input_hash="h4")

    report = guard_report()

    assert report["checked_runs"] == 9
    # the title page was never answered, so its three failures are not money paid twice
    assert report["new_duplicate_calls"] == 1 and report["total_duplicate_calls"] == 1
    assert report["new_duplicate_usd"] == "0.1000"
    assert report["reasked_windows"] == 1
    # retries after the model's own failures (one here, two on the title page) are reported
    # apart, never as waste
    assert report["retry_calls"] == 3 and report["retry_usd"] == "0.3000"
    assert {d["calls"] for d in report["duplicates"]} == {2, 3}
    assert "text" not in str(report["duplicates"])


def test_twin_editions_and_purged_paid_text_are_reported(ledger):
    source, call = ledger
    for slug in ("w-en-b2", "w-en-b2-2"):
        twin = Edition.objects.create(
            work=source.work,
            source_edition=source,
            slug=slug,
            language="en",
            edition_type=Edition.EditionType.ADAPTATION,
            status="review",
        )
        PipelineRun.objects.create(
            edition=twin,
            stage=PipelineRun.Stage.ADAPT,
            processor_version="b2-book-v1",
            input_hash="",
            idempotency_key=f"{slug}:book",
            summary={"target_level": "B2"},
        )
    stone = EditionTombstone.objects.create(
        edition_id=uuid.uuid4(),
        edition_slug="gone-b1",
        work_slug="w",
        title="A book",
        author="Author",
        language="en",
        edition_type="adaptation",
        reason="owner_request",
    )
    paid = call({"body": 1}, input_hash="p", cost="2.50")
    AIRun.objects.filter(pk=paid.pk).update(edition=None, tombstone=stone, request_payload={})

    kept = record_report()

    assert kept.twin_editions == 1 and kept.report["twins"] == [["w-en-b2", "w-en-b2-2"]]
    assert kept.purged_usd == Decimal("2.5")
    assert not kept.clean
    assert latest_report() == kept


def test_the_dashboard_shows_the_newest_report_and_runs_the_guard_on_request(
    client, ledger, monkeypatch
):
    client.force_login(get_user_model().objects.create_user(username="staff", is_staff=True))
    page = client.get(reverse("catalog:dashboard")).content.decode()
    assert "Spend guard · not run yet" in page

    record_report()
    page = client.get(reverse("catalog:dashboard")).content.decode()
    assert "0 call(s) paid twice" in page and "spend-guard-waste" not in page

    ran = []
    monkeypatch.setattr(
        "almonium_book_processor.catalog.tasks.run_spend_guard.delay", lambda: ran.append(1)
    )
    response = client.post(reverse("catalog:run-spend-guard"))
    assert response.status_code == 302 and ran == [1]
