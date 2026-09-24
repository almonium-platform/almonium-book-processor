"""Staff workflow for generating, editing and approving contextual glosses."""

from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.db.models import Count, Q
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from almonium_book_processor.catalog.glosses import (
    GLOSSABLE_BLOCK_TYPES,
    add_manual,
    current,
    queue_book,
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

# Characters of passage shown on each side of a note's phrase.
CONTEXT_CHARS = 180


def _context(note: GlossNote) -> tuple[str, str]:
    """The text just before and after the phrase, cut at word boundaries."""
    text = note.block.text
    before = text[max(0, note.start_offset - CONTEXT_CHARS) : note.start_offset]
    after = text[note.end_offset : note.end_offset + CONTEXT_CHARS]
    if note.start_offset > CONTEXT_CHARS and " " in before:
        before = "…" + before[before.index(" ") + 1 :]
    if note.end_offset + CONTEXT_CHARS < len(text) and " " in after:
        after = after[: after.rindex(" ")] + "…"
    return before, after


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
        if note.is_current:
            note.before, note.after = _context(note)
    drafts = dict(
        edition.glosses.values("chapter_id")
        .annotate(n=Count("id", filter=Q(status=GlossNote.Status.DRAFT)))
        .values_list("chapter_id", "n")
    )
    for chapter in chapters:
        chapter.draft_count = drafts.get(chapter.id, 0)
    run_states = {
        (chapter_id, status)
        for chapter_id, status in edition.pipeline_runs.filter(
            stage=PipelineRun.Stage.GLOSSES
        ).values_list("summary__chapter_id", "status")
    }
    generated = {chapter_id for chapter_id, status in run_states if status == "succeeded"}
    active = {
        chapter_id for chapter_id, status in run_states if status in {"queued", "running"}
    } - generated
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
            "book_generated": len(generated),
            "book_active": len(active),
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
def queue_book_glosses(request: HttpRequest, edition_id) -> HttpResponse:
    edition = get_object_or_404(Edition, pk=edition_id, work__visibility=Work.Visibility.PUBLIC)
    try:
        counts = queue_book(edition)
    except ValueError as error:
        messages.error(request, str(error))
    else:
        parts = [f"{counts['queued']} chapters queued or already running"]
        if counts["generated"]:
            parts.append(f"{counts['generated']} already generated")
        if counts["skipped"]:
            parts.append(f"{counts['skipped']} without prose skipped")
        messages.success(request, "Whole-book gloss generation: " + ", ".join(parts) + ".")
    chapter = edition.chapters.filter(pk=request.POST.get("chapter_id") or None).first()
    if chapter:
        return redirect(_review_url(edition.id, chapter.id))
    return redirect("catalog:gloss-review", edition_id=edition.id)


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
