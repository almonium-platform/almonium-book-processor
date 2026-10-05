from datetime import timedelta

import pytest
from django.utils import timezone

from almonium_book_processor.catalog.janitor import close_abandoned_runs
from almonium_book_processor.catalog.models import Edition, PipelineRun, Work

pytestmark = pytest.mark.django_db


def run(edition, stage, status, hours_ago):
    created = PipelineRun.objects.create(
        edition=edition,
        stage=stage,
        processor_version="test",
        input_hash="",
        idempotency_key=f"{stage}-{status}-{hours_ago}",
        status=status,
    )
    PipelineRun.objects.filter(pk=created.pk).update(
        updated_at=timezone.now() - timedelta(hours=hours_ago)
    )
    return created


def test_a_job_a_stopped_worker_left_behind_is_closed_and_says_why():
    work = Work.objects.create(slug="w", title="A book", author="Author")
    edition = Edition.objects.create(work=work, slug="w-en", language="en")
    stuck = run(edition, PipelineRun.Stage.TRANSLATE_METADATA, "running", 5)
    lost = run(edition, PipelineRun.Stage.CHAPTER_ANALYSIS, "queued", 30)
    working = run(edition, PipelineRun.Stage.ADAPT, "running", 0.5)
    # a Batch at the provider, or a promotion, is silent while it waits: not ours to close
    waiting = run(edition, PipelineRun.Stage.TRANSLATE, "running", 20)

    assert close_abandoned_runs() == 2

    for closed in (stuck, lost):
        closed.refresh_from_db()
        assert closed.status == "failed" and "Left behind" in closed.error
    for left in (working, waiting):
        left.refresh_from_db()
        assert left.status == "running"
