"""The operations page lists book steps and model calls, and a call with no end is running."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from almonium_book_processor.ai.cli_calls import on_open_account
from almonium_book_processor.catalog.models import (
    AIRun,
    Edition,
    ModelConfiguration,
    PipelineRun,
    PlanAccount,
    PromptTemplate,
    Work,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def staff(client):
    user = get_user_model().objects.create_user("editor", password="x", is_staff=True)
    client.force_login(user)
    return user


@pytest.fixture
def edition():
    work = Work.objects.create(title="A Tale of Two Cities", author="Dickens", slug="tale")
    return Edition.objects.create(
        work=work, title="A Tale of Two Cities", slug="tale-en-original", language="en"
    )


def _job(edition, *, status=PipelineRun.Status.RUNNING, summary=None, version="pilot-v1", key="a"):
    return PipelineRun.objects.create(
        edition=edition,
        stage=PipelineRun.Stage.ADAPT,
        status=status,
        idempotency_key=key,
        processor_version=version,
        input_hash="h",
        summary=summary or {},
    )


def _call(
    edition,
    job,
    *,
    provider="claude-code",
    model="claude-opus-5-5",
    prompt="chapter-analysis",
    **fields,
):
    configuration, _ = ModelConfiguration.objects.get_or_create(
        name=f"{provider}-{model}",
        defaults={"provider": provider, "model": model, "purpose": "test"},
    )
    template, _ = PromptTemplate.objects.get_or_create(
        name=prompt,
        version=1,
        defaults={"purpose": "test", "system_prompt": "x", "user_template": "y"},
    )
    return AIRun.objects.create(
        edition=edition,
        pipeline_run=job,
        model_configuration=configuration,
        prompt_template=template,
        **fields,
    )


def _page(client, **query):
    return client.get(reverse("catalog:operations"), query).content.decode()


def test_only_staff_see_it(client):
    assert client.get(reverse("catalog:operations")).status_code == 302
    assert client.get(reverse("catalog:operations-activity")).status_code == 302


def test_a_finished_call_names_its_work_model_account_and_share_of_the_week(client, staff, edition):
    PlanAccount.objects.create(provider="claude-code", account=".claude", email="me@example.com")
    job = _job(edition, summary={"chapter_title": "Chapter 3", "target_level": "B1"})
    now = timezone.now()
    _call(
        edition,
        job,
        status=AIRun.Status.SUCCEEDED,
        started_at=now - timedelta(seconds=90),
        finished_at=now,
        plan_account=".claude",
        estimated_cost_usd=Decimal("0.2308"),
    )

    page = _page(client)

    assert "Judge difficulty" in page
    assert "Chapter 3" in page
    assert "A Tale of Two Cities" in page
    assert "Opus · me" in page
    assert "1m 30s" in page
    assert "1.00% wk" in page


def test_a_call_with_no_end_runs_only_while_its_job_is_open_and_it_is_young(client, staff, edition):
    now = timezone.now()
    running = _call(edition, _job(edition), status=AIRun.Status.SUBMITTED, started_at=now)
    dead_job = _call(
        edition,
        _job(edition, status=PipelineRun.Status.SUCCEEDED, key="b"),
        status=AIRun.Status.SUBMITTED,
        started_at=now,
    )
    too_old = _call(edition, _job(edition, key="c"), status=AIRun.Status.SUBMITTED)
    AIRun.objects.filter(pk=too_old.pk).update(created_at=now - timedelta(days=1))

    page = _page(client)

    assert "1 running now" in page
    assert page.count("is-running") == 1
    assert page.count("no end recorded") == 2
    assert running.finished_at is None and dead_job.finished_at is None
    assert client.get(reverse("catalog:operations-activity")).json()["active"]


def test_book_steps_fold_their_progress_notes(client, staff, edition):
    at = timezone.now().isoformat()
    log = [
        {"at": at, "level": "B2", "step": "probe", "note": "The probe is running."},
        {"at": at, "level": "B2", "step": "write", "note": "The B2 edition is being written (1%)."},
        {"at": at, "level": "B2", "step": "write", "note": "The B2 edition is being written (9%)."},
    ]
    _job(edition, version="production-v1", summary={"log": log})

    page = _page(client, show="steps")

    assert "The probe is running." in page
    assert page.count("The B2 edition is being written.") == 1


def test_the_plan_filter_and_the_book_filter_narrow_the_list(client, staff, edition):
    other_work = Work.objects.create(title="Other", author="X", slug="other")
    other = Edition.objects.create(work=other_work, title="Other", slug="other-en", language="en")
    now = timezone.now()
    _call(edition, _job(edition), status=AIRun.Status.SUCCEEDED, started_at=now, finished_at=now)
    _call(
        other,
        _job(other, key="b"),
        provider="codex",
        model="gpt-6-astra",
        prompt="literary-b1-adaptation-pilot",
        status=AIRun.Status.SUCCEEDED,
        started_at=now,
        finished_at=now,
    )

    assert "Write B1 text" not in _page(client, show="claude-code")
    assert "Judge difficulty" not in _page(client, show="codex")
    assert "Write B1 text" not in _page(client, book=str(edition.work_id))


def test_the_answer_says_which_account_gave_it():
    answer = on_open_account("Codex", [Path("/home/ok/.codex-2")], lambda account: {"status": "ok"})

    assert answer["plan_account"] == ".codex-2"


def test_usage_keeps_the_account_that_answered():
    run = AIRun()
    usage = dict(
        input_tokens=1,
        cached_input_tokens=0,
        output_tokens=1,
        reasoning_tokens=0,
        estimated_cost_usd=Decimal("0"),
    )
    run.add_attempt_usage(**usage, plan_account=".codex-2")
    run.add_attempt_usage(**usage)

    assert run.plan_account == ".codex-2"


def test_the_entries_tab_shows_the_dictionary_by_language_and_by_writer(
    client, staff, settings, tmp_path
):
    import json

    status = tmp_path / "status.json"
    status.write_text(
        json.dumps(
            {
                "built_at": timezone.now().isoformat(),
                "queue": "v4-new",
                "languages": [
                    {
                        "lang": "de",
                        "entries": 200,
                        "rejected": 4,
                        "by_writer": {"cc-claude-opus-5-5-v4": 190, "cc-claude-fable-5-2-v4": 10},
                        "faults": {"definition of N words": 12},
                        "with_faults": 12,
                        "last_day": 150,
                        "queue": 1000,
                        "queue_left": 800,
                        "to_mend": 9000,
                        "failed": 0,
                        "senses_per_lexeme": 2.1,
                    }
                ],
                "writers": [
                    {
                        "writer": "cc-claude-opus-5-5-v4",
                        "entries": 190,
                        "rejected": 4,
                        "model": "claude-opus-5-5",
                        "effort": "high",
                        "prompt_version": "v4",
                        "schema_version": "3",
                        "list_usd_per_entry": 0.0315,
                        "output_tokens_per_entry": 1086,
                        "first": timezone.now().isoformat(),
                        "last": timezone.now().isoformat(),
                    }
                ],
            }
        )
    )
    settings.LEXICON_STATUS_FILE = str(status)

    page = _page(client, show="entries")

    assert "German" in page and "Opus-5.5 · v4 190" in page and "Fable-5.2 · v4 10" in page
    assert "definition too short or long 6%" in page
    assert "800 <small>of 1000 (20% done)</small>" in page
    assert "claude-opus-5-5" in page and "$0.0315" in page and "stale" not in page


def test_the_entries_tab_says_where_the_status_comes_from_when_there_is_none(
    client, staff, settings
):
    settings.LEXICON_STATUS_FILE = ""

    assert "No dictionary status here" in _page(client, show="entries")
