"""What an open admin page polls to follow jobs without reloading.

The admin renders server side. A page that can show a queued or running job
carries a fingerprint of everything that page would change for: the status
and progress of every pipeline run in scope, and the status of every edition
in scope. The browser polls one of the endpoints below; while the fingerprint
holds, nothing has moved and the page stays as it is. When it changes, the
page fetches itself again and swaps the new markup in, so an editor watches a
job finish where a reload used to be needed.

The scope is a work for an edition page (a translation job runs on the
companion, and the rail shows every sibling's status) and a visibility for a
catalogue list.
"""

from __future__ import annotations

from hashlib import sha256

from django.contrib.admin.views.decorators import staff_member_required
from django.http import HttpRequest, HttpResponseBadRequest, JsonResponse
from django.shortcuts import get_object_or_404

from almonium_book_processor.catalog.models import Edition, PipelineRun, Work

ACTIVE_STATUSES = (PipelineRun.Status.QUEUED, PipelineRun.Status.RUNNING)


def _fingerprint(editions, runs, run_fields: tuple[str, ...]) -> str:
    """One string that differs whenever a run or an edition in scope has moved.

    A run's ``updated_at`` is left out on purpose: a job may save a run it has
    not visibly changed, and that must not make every open page re-render.
    """

    digest = sha256()
    for edition in editions.order_by("id").values_list("id", "status", "updated_at"):
        digest.update(repr(edition).encode())
    for run in runs.order_by("id").values_list("id", *run_fields):
        digest.update(repr(run).encode())
    return digest.hexdigest()[:16]


def _payload(editions, runs, run_fields: tuple[str, ...]) -> dict:
    active = runs.filter(status__in=ACTIVE_STATUSES).order_by("-created_at")
    return {
        "fingerprint": _fingerprint(editions, runs, run_fields),
        "active": [
            {
                "id": str(run.id),
                "edition": str(run.edition_id),
                "stage": run.get_stage_display(),
                "status": run.get_status_display(),
                "progress": run.progress,
            }
            for run in active
        ],
    }


def work_activity(work: Work) -> dict:
    """An edition page follows every run of its work.

    Progress is coarse and a run's summary carries the counters the page
    prints (windows done, chunks done), so both are part of the fingerprint.
    """

    editions = Edition.objects.filter(work=work)
    runs = PipelineRun.objects.filter(edition__work=work)
    return _payload(editions, runs, ("status", "progress", "summary", "error"))


def catalogue_activity(visibility: str) -> dict:
    """A list follows only the runs it draws: the active ones.

    A finished run leaves the active set, which is change enough; hashing
    every run a catalogue has ever made would be paid on each poll.
    """

    editions = Edition.objects.filter(work__visibility=visibility)
    runs = PipelineRun.objects.filter(
        edition__work__visibility=visibility, status__in=ACTIVE_STATUSES
    )
    return _payload(editions, runs, ("status", "progress"))


@staff_member_required
def edition_activity(request: HttpRequest, edition_id: str) -> JsonResponse:
    edition = get_object_or_404(Edition.objects.select_related("work"), id=edition_id)
    return JsonResponse(work_activity(edition.work))


@staff_member_required
def catalogue_activity_view(request: HttpRequest) -> JsonResponse:
    visibility = request.GET.get("visibility", "")
    if visibility not in Work.Visibility.values:
        return HttpResponseBadRequest("visibility must be public or private")
    return JsonResponse(catalogue_activity(visibility))
