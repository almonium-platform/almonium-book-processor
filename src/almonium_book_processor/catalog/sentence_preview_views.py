from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods, require_POST

from almonium_book_processor.catalog.models import Edition, Work
from almonium_book_processor.catalog.offline_sentence_alignment import available_models
from almonium_book_processor.catalog.parallel_content import inherited_payload
from almonium_book_processor.catalog.passage_provenance import passage_provenance
from almonium_book_processor.processing.sentence_correspondence import VERSION


@staff_member_required
@require_http_methods(["GET", "POST"])
def sentence_preview(request, edition_id, other_id):
    editions = Edition.objects.filter(work__visibility=Work.Visibility.PUBLIC)
    primary = get_object_or_404(editions, pk=edition_id)
    secondary = get_object_or_404(editions, pk=other_id, work=primary.work)
    payload = inherited_payload(primary, secondary)
    if payload is None:
        raise Http404("No complete inherited pair")
    if request.method == "POST":
        from almonium_book_processor.catalog.offline_sentence_alignment import queue_alignment

        try:
            run = queue_alignment(primary.id, secondary.id, model=request.POST.get("model") or None)
            messages.success(
                request,
                f"Offline sentence alignment: {run.get_status_display()}. No paid API calls.",
            )
        except ValueError as error:
            messages.error(request, str(error))
        return redirect(request.get_full_path())
    chapters = list(primary.chapters.order_by("sequence"))
    try:
        chapter = int(request.GET.get("chapter", chapters[0].sequence))
    except ValueError:
        raise Http404("Invalid chapter") from None
    payload["blocks"] = [b for b in payload["blocks"] if b["chapter"] == chapter]
    provenance = passage_provenance(
        list(primary.blocks.filter(chapter__sequence=chapter))
        + list(secondary.blocks.filter(chapter__sequence=chapter))
    )
    for block in payload["blocks"]:
        block["primary_provenance"] = provenance[(primary.id, block["primary_block_id"])]
        block["secondary_provenance"] = provenance[(secondary.id, block["secondary_block_id"])]
    return render(
        request,
        "catalog/sentence_preview.html",
        {
            "payload": payload,
            "models": available_models(),
            "primary": primary,
            "secondary": secondary,
            "chapters": chapters,
            "chapter": chapter,
            "alignment_run": primary.pipeline_runs.filter(
                summary__method=VERSION, summary__secondary_id=str(secondary.id)
            ).first(),
        },
    )


@staff_member_required
@require_POST
def queue_sentence_alignment(request, edition_id, other_id):
    """Queue the offline sentence job for one companion pair from the edition page."""

    from almonium_book_processor.catalog.offline_sentence_alignment import queue_alignment

    edition = get_object_or_404(Edition, pk=edition_id)
    other = get_object_or_404(Edition, pk=other_id, work=edition.work)
    try:
        run = queue_alignment(edition.id, other.id, model=request.POST.get("model") or None)
        messages.success(
            request,
            f"Offline sentence alignment with {other.language.upper()}: "
            f"{run.get_status_display()}. No paid API calls.",
        )
    except ValueError as error:
        messages.error(request, str(error))
    return redirect(reverse("catalog:edition-detail", args=[edition.id]) + "#parallel-companions")
