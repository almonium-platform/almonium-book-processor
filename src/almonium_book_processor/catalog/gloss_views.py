"""Staff workflow for generating, editing and approving contextual glosses."""

from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.db.models import Count, Q, Sum
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from almonium_book_processor.catalog import estimates
from almonium_book_processor.catalog.glosses import (
    GLOSSABLE_BLOCK_TYPES,
    add_manual,
    chapter_snapshot,
    current,
    generation_spec,
    input_hash,
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
from almonium_book_processor.catalog.spend import format_usd

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
    status = _book_status(edition, chapters)
    run = (
        edition.pipeline_runs.filter(
            stage=PipelineRun.Stage.GLOSSES, summary__chapter_id=str(selected.id)
        )
        .annotate(cost_usd=Sum("ai_runs__estimated_cost_usd"))
        .order_by("-created_at")
        .first()
    )
    regenerate = selected.id in status["generated"]
    return render(
        request,
        "catalog/gloss_review.html",
        {
            "edition": edition,
            "chapters": chapters,
            "chapter": selected,
            "notes": notes,
            "run": run,
            "run_cost": format_usd(run.cost_usd) if run and run.cost_usd is not None else "",
            "regenerate": regenerate,
            "chapter_estimate": estimates.gloss_chapter(
                selected, status["sources"].get(selected.id)
            ),
            "book_estimate": estimates.gloss_book(status["left"]),
            "book_left": len(status["left"]),
            "book_active": len(status["active"]),
            "book_helper": _book_helper(chapters, status),
            "blocks": selected.blocks.filter(block_type__in=GLOSSABLE_BLOCK_TYPES).order_by(
                "sequence"
            ),
        },
    )


def _book_status(edition: Edition, chapters: list[Chapter]) -> dict:
    """Which chapters are generated for their current text, running, or still to pay for."""
    spec = generation_spec()
    sources, hashes = {}, {}
    for chapter in chapters:
        try:
            sources[chapter.id] = chapter_snapshot(chapter)
        except ValueError:
            continue
        hashes[chapter.id] = input_hash(sources[chapter.id], spec)
    runs = edition.pipeline_runs.filter(
        stage=PipelineRun.Stage.GLOSSES, input_hash__in=hashes.values()
    ).values_list("input_hash", "status")
    by_hash: dict[str, set] = {}
    for key, state in runs:
        by_hash.setdefault(key, set()).add(state)
    generated = {cid for cid, key in hashes.items() if "succeeded" in by_hash.get(key, ())}
    active = {
        cid
        for cid, key in hashes.items()
        if by_hash.get(key, set()) & {"queued", "running"} and cid not in generated
    }
    left = [
        (chapter, sources[chapter.id])
        for chapter in chapters
        if chapter.id in hashes and chapter.id not in generated | active
    ]
    return {"sources": sources, "generated": generated, "active": active, "left": left}


def _book_helper(chapters: list[Chapter], status: dict) -> str:
    """One line under the whole-book button: what is left, and what will not be charged."""
    left, active = len(status["left"]), len(status["active"])
    done = [c.sequence for c in chapters if c.id in status["generated"]]
    parts = []
    if left:
        parts.append(f"{left} chapter{'s' * (left != 1)} left.")
    elif not active:
        parts.append("Every chapter is generated.")
    if active:
        parts.append(f"{active} in progress.")
    if done and left:
        if len(done) == 1:
            parts.append(f"Chapter {done[0]} is already generated and won’t be charged again.")
        elif len(done) <= 3:
            listed = ", ".join(map(str, done[:-1])) + f" and {done[-1]}"
            parts.append(f"Chapters {listed} are already generated and won’t be charged again.")
        else:
            parts.append(f"{len(done)} generated chapters won’t be charged again.")
    return " ".join(parts)


@staff_member_required
@require_POST
def queue_glosses(request: HttpRequest, edition_id) -> HttpResponse:
    edition = get_object_or_404(Edition, pk=edition_id, work__visibility=Work.Visibility.PUBLIC)
    chapter = get_object_or_404(Chapter, pk=request.POST.get("chapter_id"), edition=edition)
    try:
        run = queue_chapter(chapter.id, regenerate=request.POST.get("regenerate") == "1")
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
