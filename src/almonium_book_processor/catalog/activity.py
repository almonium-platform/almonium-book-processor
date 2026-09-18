"""What an open admin page polls to follow jobs without reloading.

The admin renders server side. A page that can show a queued or running job
carries a fingerprint of everything that page would change for: the status
and progress of every pipeline run in scope, the AI calls those runs make,
and the status of every edition in scope. The browser polls one of the
endpoints below; while the fingerprint holds, nothing has moved and the page
stays as it is. When it changes, the page fetches itself again and swaps the
new markup in, so an editor watches a job finish where a reload used to be
needed.

Scopes: a work for any page about one edition (a translation job runs on the
companion, and the rail shows every sibling's status), a visibility for a
catalogue list, and the removal record for the removed-books page.
"""

from __future__ import annotations

from hashlib import sha256

from django.contrib.admin.views.decorators import staff_member_required
from django.db.models import Count, Max
from django.http import HttpRequest, HttpResponseBadRequest, JsonResponse
from django.shortcuts import get_object_or_404

from almonium_book_processor.catalog.models import (
    AIRun,
    Edition,
    EditionTombstone,
    PipelineRun,
    Work,
)

ACTIVE_STATUSES = (PipelineRun.Status.QUEUED, PipelineRun.Status.RUNNING)


def _fingerprint(*parts) -> str:
    """One string that differs whenever anything in ``parts`` has moved.

    Each part is an iterable of tuples in a stable order. A run's
    ``updated_at`` is deliberately never one of them: a job may save a run it
    has not visibly changed, and that must not make every open page re-render.
    """

    digest = sha256()
    for part in parts:
        for row in part:
            digest.update(repr(row).encode())
    return digest.hexdigest()[:16]


def _editions(editions):
    return editions.order_by("id").values_list("id", "status", "updated_at")


def _active(runs) -> list[dict]:
    return [
        {
            "id": str(run.id),
            "edition": str(run.edition_id),
            "stage": run.get_stage_display(),
            "status": run.get_status_display(),
            "progress": run.progress,
        }
        for run in runs.filter(status__in=ACTIVE_STATUSES).order_by("-created_at")
    ]


def work_activity(work: Work) -> dict:
    """Any page about one edition follows every run of its work.

    Progress is coarse and a run's summary carries the counters the page
    prints (windows done, chunks done), so both are part of the fingerprint.
    The AI calls are folded in as a count and a latest change, so a page that
    lists them (the alignment review) and the spend figures move as calls land.
    """

    editions = Edition.objects.filter(work=work)
    runs = PipelineRun.objects.filter(edition__work=work)
    ai_calls = AIRun.objects.filter(edition__work=work).aggregate(
        count=Count("id"), latest=Max("updated_at")
    )
    return {
        "fingerprint": _fingerprint(
            _editions(editions),
            runs.order_by("id").values_list("id", "status", "progress", "summary", "error"),
            [(ai_calls["count"], ai_calls["latest"])],
        ),
        "active": _active(runs),
    }


def catalogue_activity(visibility: str) -> dict:
    """A list follows only the runs it draws: the active ones.

    A finished run leaves the active set, which is change enough; hashing
    every run a catalogue has ever made would be paid on each poll.
    """

    editions = Edition.objects.filter(work__visibility=visibility)
    runs = PipelineRun.objects.filter(
        edition__work__visibility=visibility, status__in=ACTIVE_STATUSES
    )
    return {
        "fingerprint": _fingerprint(
            _editions(editions),
            runs.order_by("id").values_list("id", "status", "progress"),
        ),
        "active": _active(runs),
    }


def removed_activity() -> dict:
    """The removal record moves when a withdrawal is confirmed or a purge lands."""

    withdrawing = Edition.objects.filter(withdrawal_requested_at__isnull=False)
    tombstones = EditionTombstone.objects.aggregate(count=Count("id"), latest=Max("purged_at"))
    runs = PipelineRun.objects.filter(
        edition__withdrawal_requested_at__isnull=False, status__in=ACTIVE_STATUSES
    )
    return {
        "fingerprint": _fingerprint(
            _editions(withdrawing), [(tombstones["count"], tombstones["latest"])]
        ),
        "active": _active(runs),
    }


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


@staff_member_required
def removed_activity_view(request: HttpRequest) -> JsonResponse:
    return JsonResponse(removed_activity())
