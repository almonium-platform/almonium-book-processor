"""Staff workflow for generating, editing and approving contextual glosses."""

from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from almonium_book_processor.catalog.glosses import (
    GLOSSABLE_BLOCK_TYPES,
    add_manual,
    current,
    queue_chapter,
    review,
)
from almonium_book_processor.catalog.models import (
    Chapter,
    ContentBlock,
    Edition,
    GlossNote,
    PipelineRun,
    Work,
)


def _review_url(edition_id, chapter_id):
    return reverse("catalog:gloss-review", args=[edition_id]) + f"?chapter={chapter_id}"


@staff_member_required
def gloss_review(request: HttpRequest, edition_id) -> HttpResponse:
    edition = get_object_or_404(
        Edition.objects.select_related("work"),
        pk=edition_id,
        work__visibility=Work.Visibility.PUBLIC,
    )
    chapters = list(edition.chapters.order_by("sequence"))
    if not chapters:
        return redirect("catalog:edition-detail", edition_id=edition.id)
    selected = next(
        (chapter for chapter in chapters if str(chapter.id) == request.GET.get("chapter")),
        chapters[0],
    )
    notes = list(
        edition.glosses.filter(chapter=selected)
        .select_related("block", "reviewed_by")
        .order_by("block__sequence", "start_offset", "created_at")
    )
    for note in notes:
        note.is_current = current(note)
    run = edition.pipeline_runs.filter(
        stage=PipelineRun.Stage.GLOSSES, summary__chapter_id=str(selected.id)
    ).first()
    return render(
        request,
        "catalog/gloss_review.html",
        {
            "edition": edition,
            "chapters": chapters,
            "chapter": selected,
            "notes": notes,
            "run": run,
            "blocks": selected.blocks.filter(block_type__in=GLOSSABLE_BLOCK_TYPES).order_by(
                "sequence"
            ),
        },
    )


@staff_member_required
@require_POST
def queue_glosses(request: HttpRequest, edition_id) -> HttpResponse:
    edition = get_object_or_404(Edition, pk=edition_id, work__visibility=Work.Visibility.PUBLIC)
    chapter = get_object_or_404(Chapter, pk=request.POST.get("chapter_id"), edition=edition)
    try:
        run = queue_chapter(chapter.id)
    except ValueError as error:
        messages.error(request, str(error))
    else:
        messages.success(
            request,
            f"Contextual gloss generation {run.get_status_display().lower()} "
            f"for chapter {chapter.sequence}.",
        )
    return redirect(_review_url(edition.id, chapter.id))


@staff_member_required
@require_POST
def review_gloss(request: HttpRequest, edition_id, note_id) -> HttpResponse:
    edition = get_object_or_404(Edition, pk=edition_id, work__visibility=Work.Visibility.PUBLIC)
    note = get_object_or_404(GlossNote, pk=note_id, edition=edition)
    action = request.POST.get("action")
    if action not in {"approve", "reject"}:
        messages.error(request, "Choose approve or reject.")
    else:
        try:
            review(
                note.id,
                actor=request.user,
                approve=action == "approve",
                body=request.POST.get("body", ""),
            )
        except ValueError as error:
            messages.error(request, str(error))
        else:
            messages.success(request, "Gloss review saved.")
    return redirect(_review_url(edition.id, note.chapter_id))


@staff_member_required
@require_POST
def add_gloss(request: HttpRequest, edition_id) -> HttpResponse:
    edition = get_object_or_404(Edition, pk=edition_id, work__visibility=Work.Visibility.PUBLIC)
    chapter = get_object_or_404(Chapter, pk=request.POST.get("chapter_id"), edition=edition)
    try:
        add_manual(
            chapter,
            block_id=request.POST.get("block_id", "").strip(),
            quote=request.POST.get("quote", ""),
            body=request.POST.get("body", ""),
        )
    except (ValueError, ContentBlock.DoesNotExist) as error:
        messages.error(request, str(error))
    else:
        messages.success(request, "Draft gloss added for review.")
    return redirect(_review_url(edition.id, chapter.id))
