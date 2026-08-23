from __future__ import annotations

from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.db import connection
from django.db.models import Count, Q
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from almonium_book_processor.catalog.forms import EditionUploadForm, LegacyArtifactImportForm
from almonium_book_processor.catalog.models import Edition, PipelineRun, QAWarning, Work
from almonium_book_processor.catalog.services import (
    complete_review,
    import_legacy_artifacts,
    release_private_import,
)
from almonium_book_processor.catalog.tasks import process_book_pipeline, publish_edition


def _edition_cards(visibility: str):
    return (
        Edition.objects.filter(work__visibility=visibility)
        .select_related("work")
        .annotate(
            warning_count=Count(
                "warnings",
                filter=Q(
                    warnings__severity__in=[
                        QAWarning.Severity.WARNING,
                        QAWarning.Severity.ERROR,
                    ]
                ),
                distinct=True,
            ),
            run_count=Count("pipeline_runs", distinct=True),
        )
    )


@staff_member_required
def dashboard(request: HttpRequest) -> HttpResponse:
    return render(
        request,
        "catalog/dashboard.html",
        {
            "editions": _edition_cards(Work.Visibility.PUBLIC),
            "active_runs": PipelineRun.objects.filter(
                status__in=[PipelineRun.Status.QUEUED, PipelineRun.Status.RUNNING],
                edition__work__visibility=Work.Visibility.PUBLIC,
            ).select_related("edition")[:20],
        },
    )


@staff_member_required
def private_imports(request: HttpRequest) -> HttpResponse:
    return render(
        request,
        "catalog/private_imports.html",
        {
            "editions": _edition_cards(Work.Visibility.PRIVATE).order_by("-created_at"),
            "active_runs": PipelineRun.objects.filter(
                status__in=[PipelineRun.Status.QUEUED, PipelineRun.Status.RUNNING],
                edition__work__visibility=Work.Visibility.PRIVATE,
            ).select_related("edition", "edition__work")[:20],
        },
    )


@staff_member_required
def upload_source(request: HttpRequest) -> HttpResponse:
    form = EditionUploadForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        edition = form.save()
        messages.success(request, f"Queued source ingestion for {edition.title}.")
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
            "warnings", "pipeline_runs", "chapters", "review_decisions__reviewer"
        ),
        id=edition_id,
    )
    blocks = edition.blocks.select_related("chapter").order_by("chapter__sequence", "sequence")[
        :300
    ]
    return render(
        request,
        "catalog/edition_detail.html",
        {
            "edition": edition,
            "is_private": edition.work.visibility == Work.Visibility.PRIVATE,
            "has_blocks": edition.blocks.exists(),
            "blocks": blocks,
            "actionable_warnings": [
                warning
                for warning in edition.warnings.all()
                if warning.severity != QAWarning.Severity.INFO
            ],
            "import_notices": [
                warning
                for warning in edition.warnings.all()
                if warning.severity == QAWarning.Severity.INFO
            ],
            "current_review": next(
                (
                    decision
                    for decision in edition.review_decisions.all()
                    if decision.source_sha256 == edition.source_sha256
                ),
                None,
            ),
        },
    )


@staff_member_required
@require_POST
def complete_edition_review(request: HttpRequest, edition_id: str) -> HttpResponse:
    edition = get_object_or_404(Edition, id=edition_id)
    try:
        complete_review(
            edition=edition,
            reviewer=request.user,
            notes=request.POST.get("notes", "").strip(),
        )
    except ValueError as error:
        messages.error(request, str(error))
    else:
        messages.success(request, "Review completed. This edition is ready for the next step.")
    return redirect("catalog:edition-detail", edition_id=edition.id)


@staff_member_required
@require_POST
def publish_edition_to_almonium(request: HttpRequest, edition_id: str) -> HttpResponse:
    edition = get_object_or_404(Edition.objects.select_related("work"), id=edition_id)
    if edition.work.visibility != Work.Visibility.PUBLIC:
        messages.error(request, "Private imports are released to their owner, not published.")
    elif edition.status != Edition.Status.READY:
        messages.error(request, "Complete review before publishing this edition.")
    else:
        publish_edition.delay(str(edition.id))
        messages.success(
            request,
            "Publication queued. It will appear in Almonium after the hand-off succeeds.",
        )
    return redirect("catalog:edition-detail", edition_id=edition.id)


@staff_member_required
@require_POST
def retry_private_import(request: HttpRequest, edition_id: str) -> HttpResponse:
    edition = get_object_or_404(Edition.objects.select_related("work"), id=edition_id)
    if edition.work.visibility != Work.Visibility.PRIVATE:
        messages.error(request, "Only private imports can use this retry action.")
    elif edition.status != Edition.Status.FAILED:
        messages.error(request, "Only failed imports can be retried.")
    elif not edition.source_file:
        messages.error(request, "The original source file is no longer available.")
    else:
        process_book_pipeline.delay(str(edition.id))
        messages.success(request, "Private import reprocessing queued.")
    return redirect("catalog:edition-detail", edition_id=edition.id)


@staff_member_required
@require_POST
def release_private_import_to_owner(request: HttpRequest, edition_id: str) -> HttpResponse:
    edition = get_object_or_404(Edition.objects.select_related("work"), id=edition_id)
    try:
        release_private_import(
            edition=edition,
            reviewer=request.user,
            notes=request.POST.get("notes", "").strip(),
        )
    except ValueError as error:
        messages.error(request, str(error))
    else:
        messages.success(request, "Availability update queued for the owning user.")
    return redirect("catalog:edition-detail", edition_id=edition.id)


def health(request: HttpRequest) -> HttpResponse:
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except Exception:
        return HttpResponse("database unavailable", content_type="text/plain", status=503)
    return HttpResponse("ok", content_type="text/plain")
