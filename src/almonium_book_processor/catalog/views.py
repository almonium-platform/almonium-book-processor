from __future__ import annotations

from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.db import connection
from django.db.models import Count, Q
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render

from almonium_book_processor.catalog.forms import EditionUploadForm, LegacyArtifactImportForm
from almonium_book_processor.catalog.models import Edition, PipelineRun
from almonium_book_processor.catalog.services import import_legacy_artifacts


@staff_member_required
def dashboard(request: HttpRequest) -> HttpResponse:
    editions = Edition.objects.select_related("work").annotate(
        warning_count=Count(
            "warnings",
            filter=Q(warnings__resolved_at__isnull=True),
            distinct=True,
        ),
        run_count=Count("pipeline_runs", distinct=True),
    )
    return render(
        request,
        "catalog/dashboard.html",
        {
            "editions": editions,
            "active_runs": PipelineRun.objects.filter(
                status__in=[PipelineRun.Status.QUEUED, PipelineRun.Status.RUNNING]
            ).select_related("edition")[:20],
        },
    )


@staff_member_required
def upload_epub(request: HttpRequest) -> HttpResponse:
    form = EditionUploadForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        edition = form.save()
        messages.success(request, f"Queued EPUB ingestion for {edition.title}.")
        return redirect("catalog:edition-detail", edition_id=edition.id)
    return render(request, "catalog/upload.html", {"form": form})


@staff_member_required
def import_legacy(request: HttpRequest) -> HttpResponse:
    form = LegacyArtifactImportForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        editions = import_legacy_artifacts(form.cleaned_data["artifacts"])
        messages.success(request, f"Imported {len(editions)} normalized editions.")
        return redirect("catalog:dashboard")
    return render(request, "catalog/import_legacy.html", {"form": form})


@staff_member_required
def edition_detail(request: HttpRequest, edition_id: str) -> HttpResponse:
    edition = get_object_or_404(
        Edition.objects.select_related("work", "source_edition").prefetch_related(
            "warnings", "pipeline_runs", "chapters"
        ),
        id=edition_id,
    )
    blocks = edition.blocks.select_related("chapter").order_by("chapter__sequence", "sequence")[
        :300
    ]
    return render(
        request,
        "catalog/edition_detail.html",
        {"edition": edition, "blocks": blocks},
    )


def health(request: HttpRequest) -> HttpResponse:
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except Exception:
        return HttpResponse("database unavailable", content_type="text/plain", status=503)
    return HttpResponse("ok", content_type="text/plain")
