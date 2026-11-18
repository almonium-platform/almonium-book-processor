import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from almonium_book_processor.catalog.models import Edition, PipelineRun
from almonium_book_processor.processing.sentence_correspondence import VERSION
from tests.catalog.test_sentence_alignment import pair  # noqa: F401

pytestmark = pytest.mark.django_db


def test_dashboard_counts_latest_offline_run_per_pair(client, pair):  # noqa: F811
    original, translation = pair

    def run(edition, companion, status, *, method=VERSION, **counts):
        key = str(PipelineRun.objects.count())
        return PipelineRun.objects.create(
            edition=edition,
            stage=PipelineRun.Stage.ALIGN,
            status=status,
            idempotency_key=key,
            processor_version=method,
            input_hash=key,
            summary={"method": method, "secondary_id": str(companion.pk), **counts},
        )

    def companion(slug):
        return Edition.objects.create(
            work=original.work,
            slug=slug,
            language="fr",
            source_edition=original,
            parallel_role=Edition.ParallelRole.PARALLEL,
        )

    run(original, translation, "succeeded", highlighted_groups=900)
    run(translation, original, "succeeded", highlighted_groups=80, uncertain_groups=20)
    run(original, translation, "failed", method="sentence-pair-v2")
    waiting = companion("waiting")
    run(original, waiting, "failed")
    run(original, waiting, "queued")
    run(original, companion("running"), "running")
    run(original, companion("failed"), "failed")
    run(original, companion("illustrations"), "succeeded", paragraph_fallback_blocks=50)

    client.force_login(get_user_model().objects.create_user(username="editor", is_staff=True))
    response = client.get(reverse("catalog:dashboard"))
    assert response.status_code == 200
    assert response.context["alignment"] == {
        "version": VERSION.removeprefix("offline-sentence-"),
        "done": 2,
        "running": 1,
        "queued": 1,
        "failed": 1,
        "confirmed": 80,
        "uncertain": 20,
        "confirmed_percent": 80.0,
    }
    assert "80.0% of groups confirmed" in response.content.decode()
