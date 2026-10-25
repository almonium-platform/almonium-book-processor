import pytest

from almonium_book_processor.catalog.production import STARTS, Held, _log, _started


def test_a_hold_after_repeated_starts_names_the_error_that_stopped_the_step():
    # Dom Casmurro and O Cortiço held as "'probe B2' was started 2 times and did not finish" while
    # the log held the reason: no chapter fit the pilot limits.
    state = {"starts": {"probe B2": STARTS}, "log": []}
    _log(state, "info", "source", "The source's chapters have their levels.")
    _log(
        state,
        "warn",
        "probe",
        "ValueError: No chapter fits the pilot limits; split long chapters first.; trying again",
    )
    with pytest.raises(Held) as held:
        _started(state, "probe B2")
    assert "did not finish. Last: ValueError: No chapter fits the pilot limits" in str(held.value)
    assert str(held.value).endswith("split long chapters first.")


def test_a_hold_without_a_logged_error_keeps_the_plain_message():
    state = {"starts": {"book B1": STARTS}, "log": []}
    with pytest.raises(Held, match=r"'book B1' was started \d+ times and did not finish\.$"):
        _started(state, "book B1")


@pytest.mark.django_db
def test_a_job_refused_for_a_used_up_allowance_holds_the_book_without_a_start():
    from datetime import timedelta

    from django.utils import timezone

    from almonium_book_processor.catalog.models import Edition, PipelineRun, Work
    from almonium_book_processor.catalog.production import VERSION, _refused

    work = Work.objects.create(slug="w", title="A book", author="Author")
    source = Edition.objects.create(work=work, slug="w-en", language="en")

    def job(stage, status, error="", version="chapter-analysis", hours_ago=0.0):
        created = PipelineRun.objects.create(
            edition=source,
            stage=stage,
            processor_version=version,
            input_hash="",
            idempotency_key=f"{stage}-{status}-{error[:12]}-{hours_ago}",
            status=status,
            error=error,
        )
        PipelineRun.objects.filter(pk=created.pk).update(
            created_at=timezone.now() - timedelta(hours=hours_ago)
        )
        created.refresh_from_db()
        return created

    # a refusal from before this production is an old story
    job("chapter_analysis", "failed", "Chapter 0 window 1/1: Allowance used up: old", hours_ago=5)
    production = job("adapt", "running", version=VERSION, hours_ago=1)
    state = {"editions": {}, "starts": {}, "log": []}
    _refused(production, state, "B2")  # nothing this production started was refused

    job(
        "chapter_analysis",
        "failed",
        "Chapter 3 window 1/2: ValueError: the answer did not complete validation.",
    )
    _refused(production, state, "B2")  # a failure of its own is for the step's counters

    job(
        "chapter_analysis",
        "failed",
        "Chapter 0 window 1/1: Allowance used up: Codex returned no answer: You’ve hit your usage "
        "limit. Visit https://chatgpt.com/settings/usage or try again at Oct 30th, 2026 7:43 PM. "
        "— retry reuses validated windows.",
    )
    with pytest.raises(Held) as held:
        _refused(production, state, "B2")
    assert str(held.value).startswith(
        "The plan's allowance is used up, said the 'chapter_analysis' job: Allowance used up"
    )
    assert "Oct 30th, 2026 7:43 PM" in str(held.value)
    assert "retry reuses" not in str(held.value)
    assert str(held.value).endswith("Start the book again after the reset.")
    assert state["starts"] == {}


@pytest.mark.django_db
def test_a_job_that_could_not_reach_its_provider_holds_the_book_without_a_start():
    from datetime import timedelta

    from django.utils import timezone

    from almonium_book_processor.ai.cli_calls import NETWORK_DOWN
    from almonium_book_processor.catalog.models import Edition, PipelineRun, Work
    from almonium_book_processor.catalog.production import VERSION, Held, _refused, requeue_held

    work = Work.objects.create(slug="w2", title="A book", author="Author")
    source = Edition.objects.create(work=work, slug="w2-en", language="en")
    production = PipelineRun.objects.create(
        edition=source,
        stage="adapt",
        processor_version=VERSION,
        input_hash="",
        idempotency_key="w2:production",
        status="running",
        summary={"levels": ["B2"], "languages": [], "register": "", "sign_off": True},
    )
    PipelineRun.objects.create(
        edition=source,
        stage="adapt",
        processor_version="fidelity-audit-v1",
        input_hash="",
        idempotency_key="w2:audit",
        status="failed",
        error=f"{NETWORK_DOWN}: Claude Code exited with 1: Can't reach the API server (EAI_AGAIN)",
    )
    state = {"editions": {}, "starts": {}, "log": []}

    with pytest.raises(Held) as held:
        _refused(production, state, "B2")

    assert "could not be reached" in str(held.value)
    assert state["starts"] == {}
    # the meter's timer lifts this hold like a used-up allowance
    PipelineRun.objects.filter(pk=production.pk).update(
        status="failed",
        error=f"B2 held: {held.value}",
        finished_at=timezone.now() - timedelta(hours=1),
    )
    assert [run.edition for run in requeue_held(allowance_only=True)] == [source]
