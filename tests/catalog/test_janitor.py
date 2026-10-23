from datetime import timedelta

import pytest
from django.utils import timezone

from almonium_book_processor.catalog.janitor import close_abandoned_runs, plans_paused
from almonium_book_processor.catalog.models import Edition, PipelineRun, Work

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def plans_taken(monkeypatch):
    """The plans queue has its workers, unless a test says otherwise."""

    monkeypatch.setattr("almonium_book_processor.catalog.janitor.plans_paused", lambda: False)


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


def test_nothing_is_closed_while_the_plans_queue_is_paused(monkeypatch):
    # 24 October 2026: both Codex meters were empty, the workers were told to stop taking plan
    # steps, and two hours later a sweep failed the thirty-nine books waiting for the reset
    monkeypatch.setattr("almonium_book_processor.catalog.janitor.plans_paused", lambda: True)
    work = Work.objects.create(slug="w", title="A book", author="Author")
    edition = Edition.objects.create(work=work, slug="w-en", language="en")
    waiting = run(edition, PipelineRun.Stage.ADAPT, "running", 5)

    assert close_abandoned_runs() == 0

    waiting.refresh_from_db()
    assert waiting.status == "running"


class Inspect:
    def __init__(self, queues):
        self.queues = queues

    def active_queues(self):
        return self.queues


def test_the_plans_queue_is_paused_when_workers_answer_and_none_takes_from_it():
    taking = {"celery@yoga": [{"name": "celery"}], "plans-main@yoga": [{"name": "plans"}]}
    assert plans_paused(Inspect(taking)) is False
    paused = {"celery@yoga": [{"name": "celery"}], "plans-main@yoga": []}
    assert plans_paused(Inspect(paused)) is True
    # nobody answered: nothing is known, and the sweep goes on
    assert plans_paused(Inspect(None)) is False
    assert plans_paused(Inspect({})) is False
