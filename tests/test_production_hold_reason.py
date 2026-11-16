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


def _book(slug):
    from almonium_book_processor.catalog.models import Edition, PipelineRun, Work
    from almonium_book_processor.catalog.production import VERSION

    work = Work.objects.create(slug=slug, title="A book", author="Author")
    source = Edition.objects.create(work=work, slug=f"{slug}-en", language="en")
    production = PipelineRun.objects.create(
        edition=source,
        stage="adapt",
        processor_version=VERSION,
        input_hash="",
        idempotency_key=f"{slug}:production",
        status="running",
        summary={"levels": ["B2"], "languages": [], "register": "", "sign_off": True},
    )
    return source, production


def _job(edition, error, *, stage="chapter_analysis", version="chapter-analysis", hours_ago=0.0):
    from datetime import timedelta

    from django.utils import timezone

    from almonium_book_processor.catalog.models import PipelineRun

    job = PipelineRun.objects.create(
        edition=edition,
        stage=stage,
        processor_version=version,
        input_hash="",
        idempotency_key=f"{stage}-{error[:20]}-{hours_ago}",
        status="failed",
        error=error,
    )
    when = timezone.now() - timedelta(hours=hours_ago)
    PipelineRun.objects.filter(pk=job.pk).update(created_at=when, updated_at=when, finished_at=when)
    return job


@pytest.mark.django_db
def test_a_job_refused_for_a_used_up_allowance_makes_the_book_wait_not_hold():
    from datetime import timedelta

    from django.utils import timezone

    from almonium_book_processor.catalog.models import PipelineRun
    from almonium_book_processor.catalog.production import _refusal

    source, production = _book("w")
    PipelineRun.objects.filter(pk=production.pk).update(
        created_at=timezone.now() - timedelta(hours=1)
    )
    production.refresh_from_db()
    state = {"editions": {}, "starts": {"probe B2": 1}, "log": []}

    # a refusal from before this production is an old story
    _job(source, "Chapter 0 window 1/1: Allowance used up: old", hours_ago=5)
    assert _refusal(production, state, "B2") is None
    # a failure of its own is for the step's counters
    _job(source, "Chapter 3 window 1/2: ValueError: the answer did not complete validation.")
    assert _refusal(production, state, "B2") is None

    _job(
        source,
        "Chapter 0 window 1/1: Allowance used up: Codex returned no answer: You’ve hit your usage "
        "limit. Visit https://chatgpt.com/settings/usage or try again at Oct 30th, 2026 7:43 PM. "
        "— retry reuses validated windows.",
    )
    waiting = _refusal(production, state, "B2")

    assert waiting.startswith(
        "The plan's allowance is used up, said the 'chapter_analysis' job: Allowance used up"
    )
    assert "Oct 30th, 2026 7:43 PM" in waiting and "retry reuses" not in waiting
    assert "nothing is counted against the book" in waiting
    # the refused attempt's start is given back
    assert state["starts"] == {"probe B2": 0}
    # asked again on the next tick, it is the same refusal: no second refund
    assert _refusal(production, state, "B2") == waiting
    assert state["starts"] == {"probe B2": 0}


@pytest.mark.django_db
def test_a_refused_book_tries_again_once_the_wait_is_over():
    from datetime import timedelta

    from django.utils import timezone

    from almonium_book_processor.catalog.production import REFUSAL_RETRY, _refusal

    source, production = _book("w1")
    _job(source, "Allowance used up: You've hit your 5-hour limit")
    state = {"editions": {}, "starts": {}, "log": []}
    assert _refusal(production, state, "B2")

    for key in state["refusals"]:
        state["refusals"][key] = (timezone.now() - REFUSAL_RETRY - timedelta(minutes=1)).isoformat()

    assert _refusal(production, state, "B2") is None


@pytest.mark.django_db
def test_a_reviewer_refused_by_type_name_alone_is_a_refusal_too():
    """The translation review recorded only "AllowanceUsedUp" until 16 November 2026."""

    from almonium_book_processor.catalog.production import _refusal

    source, production = _book("w4")
    _job(source, "AllowanceUsedUp", stage="translate", version="translation-review-v3")
    state = {"editions": {}, "starts": {"review fr": 1}, "log": []}

    waiting = _refusal(production, state, "fr")

    assert waiting.startswith("The plan's allowance is used up, said the 'translate' job")
    assert state["starts"] == {"review fr": 0}


@pytest.mark.django_db
def test_a_translation_chapter_refused_by_the_plan_makes_the_language_wait():
    from almonium_book_processor.catalog.models import (
        AIRun,
        Edition,
        ModelConfiguration,
        PromptTemplate,
    )
    from almonium_book_processor.catalog.production import _refusal

    source, production = _book("w5")
    translation = Edition.objects.create(work=source.work, slug="w5-fr", language="fr")
    config = ModelConfiguration.objects.create(
        name="codex-translation-v1", provider="codex", model="gpt-6.1-sol", purpose="translation"
    )
    AIRun.objects.create(
        edition=translation,
        model_configuration=config,
        prompt_template=PromptTemplate.objects.create(
            name="translation",
            version=1,
            purpose="translation",
            system_prompt="x",
            user_template="y",
        ),
        input_hash="",
        idempotency_key="w5-fr-translation",
        status=AIRun.Status.FAILED,
        error='{"chapter-3": "Allowance used up: You\'ve hit your usage limit"}',
    )
    state = {"editions": {"fr": str(translation.id)}, "starts": {"translation fr": 2}, "log": []}

    waiting = _refusal(production, state, "fr")

    assert waiting.startswith("The plan's allowance is used up, said the 'model call' job")
    assert state["starts"] == {"translation fr": 1}
    # another language of the same book does not wait for it
    assert _refusal(production, {"editions": {}, "starts": {}, "log": []}, "es") is None


@pytest.mark.django_db
def test_a_job_that_could_not_reach_its_provider_makes_the_book_wait():
    from almonium_book_processor.ai.cli_calls import NETWORK_DOWN
    from almonium_book_processor.catalog.production import _refusal

    source, production = _book("w2")
    _job(
        source,
        f"{NETWORK_DOWN}: Claude Code exited with 1: Can't reach the API server (EAI_AGAIN)",
        stage="adapt",
        version="fidelity-audit-v1",
    )
    state = {"editions": {}, "starts": {}, "log": []}

    assert "could not be reached" in _refusal(production, state, "B2")


@pytest.mark.django_db
def test_a_book_whose_every_claude_account_is_paused_waits_for_one():
    from almonium_book_processor.ai.claude_code_provider import EVERY_ACCOUNT_PAUSED
    from almonium_book_processor.ai.cli_calls import AllowanceUsedUp
    from almonium_book_processor.catalog.production import _refusal

    source, production = _book("w3")
    _job(
        source,
        str(AllowanceUsedUp(EVERY_ACCOUNT_PAUSED)),
        stage="adapt",
        version="fidelity-audit-v1",
    )
    state = {"editions": {}, "starts": {}, "log": []}

    assert "No Claude account is open" in _refusal(production, state, "B2")


@pytest.mark.django_db
def test_an_older_allowance_hold_is_still_lifted_by_the_meters_timer():
    from datetime import timedelta

    from django.utils import timezone

    from almonium_book_processor.catalog.models import PipelineRun
    from almonium_book_processor.catalog.production import requeue_held

    source, production = _book("w6")
    PipelineRun.objects.filter(pk=production.pk).update(
        status="failed",
        error="B2 held: The plan's allowance is used up, said the 'adapt' job: Allowance used up",
        finished_at=timezone.now() - timedelta(hours=1),
    )
    assert [run.edition for run in requeue_held(allowance_only=True)] == [source]
