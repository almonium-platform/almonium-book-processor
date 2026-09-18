"""The activity endpoints an open page polls to follow jobs without reloading."""

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from almonium_book_processor.catalog.activity import (
    catalogue_activity,
    removed_activity,
    work_activity,
)
from almonium_book_processor.catalog.models import (
    AIRun,
    Edition,
    EditionTombstone,
    ModelConfiguration,
    PipelineRun,
    PromptTemplate,
    Work,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def staff():
    user = get_user_model().objects.create_user("editor", "editor@example.test", "pw")
    user.is_staff = True
    user.save(update_fields=["is_staff"])
    return user


@pytest.fixture
def work():
    return Work.objects.create(
        slug="shelley-frankenstein",
        title="Frankenstein",
        author="Mary Shelley",
        original_language="en",
    )


@pytest.fixture
def edition(work):
    return Edition.objects.create(
        work=work,
        slug="shelley-frankenstein-en",
        title="Frankenstein",
        author="Mary Shelley",
        language="en",
        parallel_role="canonical",
        status="processing",
        source_sha256="a" * 64,
    )


def _run(edition, **fields):
    defaults = {
        "stage": PipelineRun.Stage.INGEST,
        "idempotency_key": f"{edition.id}-{PipelineRun.objects.count()}",
        "processor_version": "v1",
        "input_hash": "b" * 64,
    }
    return PipelineRun.objects.create(edition=edition, **{**defaults, **fields})


def test_fingerprint_moves_with_progress_status_and_the_edition(edition):
    run = _run(edition, status=PipelineRun.Status.RUNNING, progress=5)
    before = work_activity(edition.work)

    run.progress = 35
    run.save(update_fields=["progress", "updated_at"])
    progressed = work_activity(edition.work)
    assert progressed["fingerprint"] != before["fingerprint"]
    assert progressed["active"] == [
        {
            "id": str(run.id),
            "edition": str(edition.id),
            "stage": "Source ingestion",
            "status": "Running",
            "progress": 35,
        }
    ]

    run.status = PipelineRun.Status.SUCCEEDED
    run.progress = 100
    run.save(update_fields=["status", "progress", "updated_at"])
    finished = work_activity(edition.work)
    assert finished["fingerprint"] != progressed["fingerprint"]
    assert finished["active"] == []

    edition.status = Edition.Status.REVIEW
    edition.save(update_fields=["status", "updated_at"])
    assert work_activity(edition.work)["fingerprint"] != finished["fingerprint"]


def test_fingerprint_ignores_a_save_that_changed_nothing_visible(edition):
    run = _run(edition, status=PipelineRun.Status.RUNNING, progress=5)
    before = work_activity(edition.work)["fingerprint"]
    run.save(update_fields=["updated_at"])
    assert work_activity(edition.work)["fingerprint"] == before


def test_work_scope_moves_as_ai_calls_land(edition):
    """The alignment review lists AI runs and the rail prints spend: both follow."""

    before = work_activity(edition.work)["fingerprint"]
    call = AIRun.objects.create(
        edition=edition,
        model_configuration=ModelConfiguration.objects.create(
            name="judge", provider="openai", model="gpt-5-mini", purpose="judge"
        ),
        prompt_template=PromptTemplate.objects.create(
            name="judge", version=1, purpose="judge", system_prompt="s", user_template="u"
        ),
        status=AIRun.Status.QUEUED,
    )
    queued = work_activity(edition.work)["fingerprint"]
    assert queued != before
    call.status = AIRun.Status.SUCCEEDED
    call.save(update_fields=["status", "updated_at"])
    assert work_activity(edition.work)["fingerprint"] != queued


def test_removed_scope_follows_withdrawals_and_purges(edition):
    before = removed_activity()["fingerprint"]
    edition.withdrawal_requested_at = edition.updated_at
    edition.save(update_fields=["withdrawal_requested_at", "updated_at"])
    requested = removed_activity()
    assert requested["fingerprint"] != before

    EditionTombstone.objects.create(
        edition_id=edition.id,
        edition_slug="gone-en",
        work_slug="gone",
        title="Gone",
        author="",
        language="en",
        edition_type="original",
        reason=EditionTombstone.Reason.values[0],
    )
    assert removed_activity()["fingerprint"] != requested["fingerprint"]


def test_work_scope_covers_a_companion_translation_job(edition):
    french = Edition.objects.create(
        work=edition.work,
        source_edition=edition,
        slug="shelley-frankenstein-fr",
        language="fr",
        parallel_role="parallel",
        status="processing",
        source_sha256="c" * 64,
    )
    before = work_activity(edition.work)["fingerprint"]
    _run(french, stage=PipelineRun.Stage.TRANSLATE, status=PipelineRun.Status.QUEUED)
    after = work_activity(edition.work)
    assert after["fingerprint"] != before
    assert after["active"][0]["edition"] == str(french.id)


def test_catalogue_scope_only_sees_its_visibility(edition):
    private_work = Work.objects.create(
        slug="private-book",
        title="Private",
        author="",
        original_language="en",
        visibility="private",
    )
    private = Edition.objects.create(
        work=private_work,
        slug="private-en",
        language="en",
        status="processing",
        source_sha256="d" * 64,
    )
    public_before = catalogue_activity(Work.Visibility.PUBLIC)["fingerprint"]
    _run(private, status=PipelineRun.Status.RUNNING, progress=40)
    assert catalogue_activity(Work.Visibility.PUBLIC)["fingerprint"] == public_before
    assert catalogue_activity(Work.Visibility.PRIVATE)["active"][0]["edition"] == str(private.id)


def test_endpoints_answer_staff_only(client, staff, edition):
    edition_url = reverse("catalog:edition-activity", args=[edition.id])
    list_url = reverse("catalog:catalogue-activity")

    assert client.get(edition_url).status_code == 302
    client.force_login(staff)
    _run(edition, status=PipelineRun.Status.RUNNING, progress=5)

    payload = client.get(edition_url).json()
    assert payload["fingerprint"] == work_activity(edition.work)["fingerprint"]
    assert payload["active"][0]["stage"] == "Source ingestion"

    payload = client.get(list_url, {"visibility": "public"}).json()
    assert payload["active"][0]["edition"] == str(edition.id)
    assert client.get(list_url, {"visibility": "everything"}).status_code == 400


def test_pages_carry_the_fingerprint_they_were_rendered_with(client, staff, edition):
    client.force_login(staff)
    _run(edition, status=PipelineRun.Status.RUNNING, progress=5)

    page = client.get(reverse("catalog:edition-detail", args=[edition.id])).content.decode()
    assert f'data-live-fingerprint="{work_activity(edition.work)["fingerprint"]}"' in page
    assert reverse("catalog:edition-activity", args=[edition.id]) in page
    assert 'class="live-badge"' in page

    page = client.get(reverse("catalog:dashboard")).content.decode()
    fingerprint = catalogue_activity(Work.Visibility.PUBLIC)["fingerprint"]
    assert f'data-live-fingerprint="{fingerprint}"' in page

    page = client.get(reverse("catalog:removed-books")).content.decode()
    assert f'data-live-fingerprint="{removed_activity()["fingerprint"]}"' in page
    assert client.get(reverse("catalog:removed-activity")).json()["active"] == []

    page = client.get(reverse("catalog:edition-reader", args=[edition.id])).content.decode()
    assert reverse("catalog:edition-activity", args=[edition.id]) in page
