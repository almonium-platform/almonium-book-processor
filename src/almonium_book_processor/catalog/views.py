from __future__ import annotations

import uuid
from collections import defaultdict
from urllib.parse import quote

from django.conf import settings
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.db import connection
from django.db.models import Count, Q
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from almonium_book_processor.catalog.ai_translation import (
    create_parallel_translation,
    last_translation_mode,
    last_translation_tier,
)
from almonium_book_processor.catalog.forms import (
    EditionUploadForm,
    LegacyArtifactImportForm,
    ParallelTranslationForm,
)
from almonium_book_processor.catalog.models import (
    AlignmentGroupReview,
    BlockAlignment,
    ChapterAlignment,
    ContentBlock,
    Edition,
    PipelineRun,
    QAWarning,
    TextQualityFinding,
    Work,
)
from almonium_book_processor.catalog.services import (
    BULK_DETACHED_INITIAL_MIN_CONFIDENCE,
    apply_high_confidence_detached_initials,
    apply_text_quality_finding,
    complete_review,
    confirm_ai_alignment_groups,
    dismiss_text_quality_finding,
    import_legacy_artifacts,
    release_private_import,
    repair_alignment_group,
    resolve_review_warning,
    review_alignment_chapter,
    review_alignment_group,
    revise_block_text,
    translate_coverage_gap,
)
from almonium_book_processor.catalog.tasks import (
    align_edition_to_source,
    analyze_edition_lexicon,
    analyze_edition_source_quality,
    prepare_ai_alignment,
    prepare_translation,
    process_book_pipeline,
    process_normalized_edition,
    publish_edition,
    translate_edition_inline,
)


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
                    ],
                    warnings__resolved_at__isnull=True,
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
            "warnings",
            "pipeline_runs",
            "chapters",
            "review_decisions__reviewer",
            "artifacts",
            "text_quality_findings__block",
            "block_revisions__editor",
        ),
        id=edition_id,
    )
    blocks = edition.blocks.select_related("chapter").order_by("chapter__sequence", "sequence")[
        :300
    ]
    pipeline_runs = list(edition.pipeline_runs.all())
    source_qa_artifacts = edition.artifacts.filter(kind="source_qa")
    source_qa_artifact = source_qa_artifacts.filter(is_current=True).first()
    text_quality_findings = edition.text_quality_findings.filter(
        status=TextQualityFinding.Status.OPEN
    )
    tree_root = edition if edition.is_canonical else edition.source_edition
    parallel_editions = (
        Edition.objects.filter(
            work=edition.work,
            parallel_role__in=[
                Edition.ParallelRole.CANONICAL,
                Edition.ParallelRole.PARALLEL,
            ],
        )
        .exclude(id=edition.id)
        .order_by("parallel_role", "language")
        if tree_root is not None
        else Edition.objects.none()
    )
    return render(
        request,
        "catalog/edition_detail.html",
        {
            "edition": edition,
            "is_private": edition.work.visibility == Work.Visibility.PRIVATE,
            "has_blocks": edition.blocks.exists(),
            "blocks": blocks,
            "pipeline_run_count": len(pipeline_runs),
            "recent_pipeline_runs": pipeline_runs[:3],
            "older_pipeline_runs": pipeline_runs[3:],
            "actionable_warnings": [
                warning
                for warning in edition.warnings.all()
                if warning.severity != QAWarning.Severity.INFO and warning.resolved_at is None
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
            "lexical_profile": edition.artifacts.filter(
                kind="lexical_profile", is_current=True
            ).first(),
            "useful_words": edition.artifacts.filter(kind="useful_words", is_current=True).first(),
            "source_qa_artifact": source_qa_artifact,
            "has_source_qa_history": source_qa_artifacts.exists(),
            "text_quality_findings": text_quality_findings,
            "bulk_detached_initial_count": text_quality_findings.filter(
                code="detached_initial",
                confidence__gte=BULK_DETACHED_INITIAL_MIN_CONFIDENCE,
                block__isnull=False,
                start_offset__isnull=False,
                end_offset__isnull=False,
            ).count(),
            "recent_revisions": edition.block_revisions.all()[:10],
            "translation_form": (
                ParallelTranslationForm(source_edition=edition)
                if edition.is_canonical and edition.blocks.exists()
                else None
            ),
            "parallel_editions": parallel_editions,
            "inferred_alignment_available": (
                edition.parallel_role == Edition.ParallelRole.STANDALONE
                and edition.source_edition is not None
            ),
            "has_inferred_alignment": (
                edition.source_edition is not None
                and BlockAlignment.objects.filter(target_edition=edition).exists()
            ),
        },
    )


READER_SEARCH_LIMIT = 200


def _reader_redirect(
    edition_id: str, chapter: str, query: str = "", block_id: str = "", parallel: str = ""
) -> HttpResponse:
    url = f"{reverse('catalog:edition-reader', args=[edition_id])}?chapter={chapter}"
    if query:
        url += f"&q={quote(query)}"
    if parallel:
        url += f"&parallel={quote(parallel)}"
    if block_id:
        url += f"#block-{block_id}"
    return redirect(url)


def _parallel_options(edition: Edition) -> list[Edition]:
    """Editions that share this edition's canonical block groups."""

    if not edition.supports_parallel_reading:
        return []
    return list(
        Edition.objects.filter(
            work=edition.work,
            parallel_role__in=[Edition.ParallelRole.CANONICAL, Edition.ParallelRole.PARALLEL],
        )
        .exclude(id=edition.id)
        .order_by("parallel_role", "language")
    )


def _parallel_rows(
    blocks: list[ContentBlock], parallel_edition: Edition | None, chapter: int | None
) -> tuple[list[dict], int]:
    """Pair each block with its counterpart through the canonical align group.

    Correspondence in a generated edition is inherited rather than inferred, so
    a block that fails to pair is a defect in the translation and not a
    low-confidence guess. Every such case gets its own row, including blocks the
    other edition has and this one does not, so nothing can be scrolled past.
    """

    if parallel_edition is None:
        return [{"block": block, "counterparts": [], "status": "paired"} for block in blocks], 0

    other = parallel_edition.language.upper()
    groups = {block.align_group for block in blocks if block.align_group}
    counterparts: dict[uuid.UUID, list[ContentBlock]] = defaultdict(list)
    for block in parallel_edition.blocks.select_related("chapter").filter(align_group__in=groups):
        counterparts[block.align_group].append(block)

    rows: list[dict] = []
    for block in blocks:
        matched = counterparts.get(block.align_group, []) if block.align_group else []
        if not block.align_group:
            status, label = "ungrouped", "No group"
            note = (
                "This block carries no canonical group, so it can never pair. "
                "The canonical edition needs its groups re-seeded."
            )
        elif not matched:
            status, label = "missing", f"Missing in {other}"
            note = f"No block in the {other} edition carries this group."
        elif len(matched) > 1:
            status, label = "duplicate", f"Duplicated in {other}"
            note = f"{len(matched)} blocks in the {other} edition claim this group."
        else:
            status, label, note = "paired", "", ""
        rows.append(
            {
                "block": block,
                "counterparts": matched,
                "status": status,
                "label": label,
                "note": note,
            }
        )

    # Blocks the other edition has here and this one does not. Only meaningful
    # while reading a single chapter; search results have no chapter frame.
    if chapter is not None:
        for block in parallel_edition.blocks.select_related("chapter").filter(
            chapter__sequence=chapter
        ):
            if block.align_group and block.align_group in groups:
                continue
            rows.append(
                {
                    "block": None,
                    "counterparts": [block],
                    "status": "extra",
                    "label": f"Extra in {other}",
                    "note": (
                        f"The {other} edition has this block in chapter {chapter} but no block "
                        "here carries its group."
                    ),
                }
            )

    return rows, sum(1 for row in rows if row["status"] != "paired")


@staff_member_required
def edition_reader(request: HttpRequest, edition_id: str) -> HttpResponse:
    """Read the whole normalized text of any edition and correct blocks in place.

    This is deliberately independent of alignment: a generated parallel edition
    has no alignment queue, and polishing the text is a prerequisite for
    alignment rather than a part of it.
    """

    edition = get_object_or_404(
        Edition.objects.select_related("work", "source_edition"), id=edition_id
    )
    chapters = list(edition.chapters.order_by("sequence"))
    query = request.GET.get("q", "").strip()

    if query:
        blocks = list(
            edition.blocks.select_related("chapter")
            .filter(Q(block_id__icontains=query) | Q(text__icontains=query))
            .order_by("chapter__sequence", "sequence")[:READER_SEARCH_LIMIT]
        )
        match_count = (
            edition.blocks.filter(Q(block_id__icontains=query) | Q(text__icontains=query))
            .order_by()
            .count()
        )
        chapter = blocks[0].chapter.sequence if blocks else None
    else:
        chapter_numbers = [item.sequence for item in chapters]
        try:
            requested = int(request.GET.get("chapter", ""))
        except ValueError:
            requested = None
        chapter = requested if requested in chapter_numbers else next(iter(chapter_numbers), None)
        blocks = (
            list(
                edition.blocks.select_related("chapter")
                .filter(chapter__sequence=chapter)
                .order_by("sequence")
            )
            if chapter is not None
            else []
        )
        match_count = len(blocks)

    parallel_options = _parallel_options(edition)
    requested_parallel = request.GET.get("parallel", "").strip()
    parallel_edition = next(
        (option for option in parallel_options if str(option.id) == requested_parallel), None
    )
    rows, gap_count = _parallel_rows(blocks, parallel_edition, None if query else chapter)

    positions = {item.sequence: index for index, item in enumerate(chapters)}
    current_index = positions.get(chapter)
    return render(
        request,
        "catalog/reader.html",
        {
            "edition": edition,
            "chapters": chapters,
            "chapter": chapter,
            "current_chapter": chapters[current_index] if current_index is not None else None,
            "previous_chapter": (
                chapters[current_index - 1] if current_index else None  # index 0 has no previous
            ),
            "next_chapter": (
                chapters[current_index + 1]
                if current_index is not None and current_index + 1 < len(chapters)
                else None
            ),
            "blocks": blocks,
            "rows": rows,
            "parallel_options": parallel_options,
            "parallel_edition": parallel_edition,
            "parallel_param": f"&parallel={parallel_edition.id}" if parallel_edition else "",
            "gap_count": gap_count,
            "query": query,
            "match_count": match_count,
            "truncated": bool(query) and match_count > len(blocks),
            "search_limit": READER_SEARCH_LIMIT,
            "block_count": edition.blocks.count(),
            "recent_revisions": edition.block_revisions.select_related("editor")[:10],
        },
    )


@staff_member_required
@require_POST
def edit_block_text(request: HttpRequest, edition_id: str, block_id: uuid.UUID) -> HttpResponse:
    edition = get_object_or_404(Edition, id=edition_id)
    try:
        revise_block_text(
            edition=edition,
            block_id=block_id,
            revised_text=request.POST.get("text", ""),
            editor=request.user,
            notes=request.POST.get("notes", "").strip(),
        )
    except ValueError as error:
        messages.error(request, str(error))
    else:
        messages.success(request, "Block text updated; derived data was queued for a refresh.")
    return _reader_redirect(
        str(edition.id),
        request.POST.get("chapter", ""),
        request.POST.get("q", ""),
        str(block_id),
        request.POST.get("parallel", ""),
    )


@staff_member_required
@require_POST
def queue_lexical_analysis(request: HttpRequest, edition_id: str) -> HttpResponse:
    edition = get_object_or_404(Edition, id=edition_id)
    analyze_edition_lexicon.delay(str(edition.id))
    messages.success(request, "Lexical analysis queued.")
    return redirect("catalog:edition-detail", edition_id=edition.id)


@staff_member_required
@require_POST
def queue_source_quality_scan(request: HttpRequest, edition_id: str) -> HttpResponse:
    edition = get_object_or_404(Edition, id=edition_id)
    analyze_edition_source_quality.delay(str(edition.id))
    messages.success(request, "Source-text QA scan queued.")
    return redirect("catalog:edition-detail", edition_id=edition.id)


@staff_member_required
@require_POST
def approve_detached_initials(request: HttpRequest, edition_id: str) -> HttpResponse:
    edition = get_object_or_404(Edition, id=edition_id)
    try:
        revisions = apply_high_confidence_detached_initials(
            edition=edition,
            reviewer=request.user,
        )
    except ValueError as error:
        messages.error(request, str(error))
    else:
        messages.success(
            request,
            f"Applied {len(revisions)} detached-initial corrections with audit revisions; "
            "derived data refresh queued.",
        )
    return redirect("catalog:edition-detail", edition_id=edition.id)


@staff_member_required
@require_POST
def queue_source_alignment(request: HttpRequest, edition_id: str) -> HttpResponse:
    """Infer alignment between two independently imported texts.

    Generated parallel editions never need this: they inherit canonical block
    groups at translation time. It stays available for imported pairs.
    """

    edition = get_object_or_404(Edition, id=edition_id, source_edition__isnull=False)
    if not edition.requires_inferred_alignment:
        messages.error(
            request,
            "This edition is aligned by construction. Inferred alignment applies only to "
            "standalone editions imported from a separate source.",
        )
        return redirect("catalog:edition-detail", edition_id=edition.id)
    align_edition_to_source.delay(str(edition.id))
    messages.success(request, "Inferred alignment queued.")
    return redirect("catalog:edition-detail", edition_id=edition.id)


@staff_member_required
@require_POST
def queue_parallel_translation(request: HttpRequest, edition_id: str) -> HttpResponse:
    """Generate a block-for-block parallel edition from a canonical original."""

    source = get_object_or_404(Edition.objects.select_related("work"), id=edition_id)
    form = ParallelTranslationForm(request.POST, source_edition=source)
    if not form.is_valid():
        messages.error(request, "; ".join(form.errors.get("__all__", ["Check the form."])))
        return redirect("catalog:edition-detail", edition_id=source.id)
    try:
        edition = create_parallel_translation(
            source_edition=source,
            target_language=form.cleaned_data["target_language"],
            register=form.cleaned_data["register"],
            tier=form.cleaned_data["tier"],
        )
    except ValueError as error:
        messages.error(request, str(error))
        return redirect("catalog:edition-detail", edition_id=source.id)
    tier = form.cleaned_data["tier"]
    if form.cleaned_data["mode"] == "batch":
        prepare_translation.delay(str(edition.id), tier=tier)
        note = "Batch results can take up to 24 hours; the edition fills in when they arrive."
    else:
        translate_edition_inline.delay(str(edition.id), tier)
        note = "Running directly; this usually finishes in a few minutes."
    messages.success(
        request,
        f"Queued a {edition.get_language_display()} parallel translation. {note}",
    )
    return redirect("catalog:edition-detail", edition_id=edition.id)


@staff_member_required
@require_POST
def apply_source_quality_finding(
    request: HttpRequest, edition_id: str, finding_id: uuid.UUID
) -> HttpResponse:
    edition = get_object_or_404(Edition, id=edition_id)
    try:
        apply_text_quality_finding(
            edition=edition,
            finding_id=finding_id,
            replacement=request.POST.get("replacement", ""),
            reviewer=request.user,
            notes=request.POST.get("notes", "").strip(),
        )
    except ValueError as error:
        messages.error(request, str(error))
    else:
        messages.success(request, "Correction applied with an audit revision; refresh queued.")
    return redirect("catalog:edition-detail", edition_id=edition.id)


@staff_member_required
@require_POST
def dismiss_source_quality_finding(
    request: HttpRequest, edition_id: str, finding_id: uuid.UUID
) -> HttpResponse:
    edition = get_object_or_404(Edition, id=edition_id)
    try:
        dismiss_text_quality_finding(
            edition=edition,
            finding_id=finding_id,
            reviewer=request.user,
        )
    except ValueError as error:
        messages.error(request, str(error))
    else:
        messages.success(request, "Source-text finding dismissed.")
    return redirect("catalog:edition-detail", edition_id=edition.id)


@staff_member_required
def alignment_review(request: HttpRequest, edition_id: str) -> HttpResponse:
    edition = get_object_or_404(
        Edition.objects.select_related("work", "source_edition"),
        id=edition_id,
        source_edition__isnull=False,
    )
    chapter_numbers = list(edition.chapters.order_by("sequence").values_list("sequence", flat=True))
    if not chapter_numbers:
        return render(
            request,
            "catalog/alignment_review.html",
            {
                "edition": edition,
                "chapter_numbers": [],
                "alignment_groups": [],
                "recent_ai_runs": edition.ai_runs.select_related("model_configuration")[:5],
                "ai_enabled": bool(settings.OPENAI_API_KEY),
            },
        )
    unresolved_warnings = list(
        edition.warnings.filter(resolved_at=None)
        .exclude(severity=QAWarning.Severity.INFO)
        .select_related("block__chapter")
    )
    all_chapter_mappings = list(
        ChapterAlignment.objects.filter(target_edition=edition).select_related(
            "source_chapter", "target_chapter"
        )
    )
    target_chapters_by_group: dict[uuid.UUID, set[int]] = defaultdict(set)
    target_chapters_by_source: dict[uuid.UUID, set[int]] = defaultdict(set)
    for mapping in all_chapter_mappings:
        target_chapters_by_group[mapping.group_id].add(mapping.target_chapter.sequence)
        target_chapters_by_source[mapping.source_chapter_id].add(mapping.target_chapter.sequence)

    warnings_by_chapter: dict[int, list[QAWarning]] = defaultdict(list)
    edition_level_warnings = []
    for warning in unresolved_warnings:
        if warning.block_id and warning.block and warning.block.chapter:
            warnings_by_chapter[warning.block.chapter.sequence].append(warning)
            continue
        if warning.source_ref.startswith("chapter-group:"):
            try:
                group_id = uuid.UUID(warning.source_ref.removeprefix("chapter-group:"))
            except ValueError:
                pass
            else:
                for target_chapter in target_chapters_by_group.get(group_id, set()):
                    warnings_by_chapter[target_chapter].append(warning)
                continue
        edition_level_warnings.append(warning)

    aligned_source_ids = set(
        BlockAlignment.objects.filter(target_edition=edition).values_list(
            "source_block_id", flat=True
        )
    )
    aligned_target_ids = set(
        BlockAlignment.objects.filter(target_edition=edition).values_list(
            "target_block_id", flat=True
        )
    )
    unmatched_source_blocks = edition.source_edition.blocks.exclude(id__in=aligned_source_ids)
    unmatched_target_blocks = edition.blocks.exclude(id__in=aligned_target_ids).select_related(
        "chapter"
    )
    coverage_gaps_by_chapter: dict[int, int] = defaultdict(int)
    for block in unmatched_source_blocks.select_related("chapter"):
        if block.chapter_id:
            for target_chapter in target_chapters_by_source.get(block.chapter_id, set()):
                warnings_by_chapter[target_chapter]
                coverage_gaps_by_chapter[target_chapter] += 1
    for block in unmatched_target_blocks:
        if block.chapter:
            warnings_by_chapter[block.chapter.sequence]
            coverage_gaps_by_chapter[block.chapter.sequence] += 1

    issue_chapter_numbers = [number for number in chapter_numbers if number in warnings_by_chapter]
    view_filter = request.GET.get("filter", "")
    visible_chapter_numbers = (
        issue_chapter_numbers
        if view_filter == "issues" and issue_chapter_numbers
        else chapter_numbers
    )
    try:
        chapter = int(request.GET.get("chapter", visible_chapter_numbers[0]))
    except (TypeError, ValueError):
        chapter = visible_chapter_numbers[0]
    if chapter not in visible_chapter_numbers:
        chapter = visible_chapter_numbers[0]

    chapter_mappings = list(
        ChapterAlignment.objects.filter(
            target_edition=edition,
            target_chapter__sequence=chapter,
        ).select_related("source_chapter", "target_chapter")
    )
    source_chapter_numbers = sorted(
        {mapping.source_chapter.sequence for mapping in chapter_mappings}
    ) or [chapter]
    source_blocks = list(
        edition.source_edition.blocks.filter(chapter__sequence__in=source_chapter_numbers).order_by(
            "chapter__sequence", "sequence"
        )
    )
    target_blocks = list(edition.blocks.filter(chapter__sequence=chapter).order_by("sequence"))
    alignments = list(
        BlockAlignment.objects.filter(
            target_edition=edition,
            target_block__chapter__sequence=chapter,
        ).select_related("source_block", "target_block")
    )
    grouped: dict[uuid.UUID, dict] = {}
    for alignment in alignments:
        group = grouped.setdefault(
            alignment.group_id,
            {
                "id": alignment.group_id,
                "confidence": alignment.confidence,
                "strategy": alignment.strategy,
                "sources": {},
                "targets": {},
            },
        )
        group["confidence"] = min(group["confidence"], alignment.confidence)
        group["sources"][alignment.source_block_id] = alignment.source_block
        group["targets"][alignment.target_block_id] = alignment.target_block

    reviews = {
        review.group_id: review
        for review in AlignmentGroupReview.objects.filter(
            target_edition=edition,
            group_id__in=grouped,
        ).select_related("reviewer")
    }
    warnings_by_block: dict[uuid.UUID, list[QAWarning]] = {}
    for warning in unresolved_warnings:
        if warning.block_id:
            warnings_by_block.setdefault(warning.block_id, []).append(warning)

    alignment_groups = []
    for group in grouped.values():
        sources = sorted(group["sources"].values(), key=lambda block: block.sequence)
        targets = sorted(group["targets"].values(), key=lambda block: block.sequence)
        confidence = group["confidence"]
        alignment_groups.append(
            {
                **group,
                "sources": sources,
                "targets": targets,
                "review": reviews.get(group["id"]),
                "warnings": [
                    warning for block in targets for warning in warnings_by_block.get(block.id, [])
                ],
                "confidence_percent": round(confidence * 100),
                "confidence_class": (
                    "high" if confidence >= 0.72 else "medium" if confidence >= 0.55 else "low"
                ),
            }
        )
    alignment_groups.sort(key=lambda group: min(block.sequence for block in group["targets"]))
    chapter_level_warnings = [
        warning for warning in warnings_by_chapter.get(chapter, []) if warning.block_id is None
    ]
    chapter_warning_count = len(warnings_by_chapter.get(chapter, []))
    if view_filter == "issues":
        if chapter_level_warnings:
            alignment_groups = [group for group in alignment_groups if not group["review"]]
        else:
            alignment_groups = [group for group in alignment_groups if group["warnings"]]

    current_group_ids = (
        BlockAlignment.objects.filter(target_edition=edition)
        .values_list("group_id", flat=True)
        .distinct()
    )
    reviews_for_current_groups = AlignmentGroupReview.objects.filter(
        target_edition=edition,
        group_id__in=current_group_ids,
    )
    total_group_count = current_group_ids.count()
    ai_approved_count = reviews_for_current_groups.filter(
        decision=AlignmentGroupReview.Decision.AI_ACCEPTED
    ).count()
    staff_approved_count = reviews_for_current_groups.exclude(
        decision=AlignmentGroupReview.Decision.AI_ACCEPTED
    ).count()
    pending_group_count = total_group_count - ai_approved_count - staff_approved_count
    ai_run_summaries = []
    for run in edition.ai_runs.select_related("model_configuration", "prompt_template")[:5]:
        uncertain_count = len(run.response_payload.get("uncertain_chapter_group_ids", []))
        tier = run.request_payload.get("tier")
        ai_run_summaries.append(
            {
                "run": run,
                "display_status": (
                    "Completed" if run.status == run.Status.SUCCEEDED else run.get_status_display()
                ),
                "outcome": (
                    f"{uncertain_count} sent to the stronger model"
                    if uncertain_count and tier == "primary"
                    else f"{uncertain_count} chapter groups still need review"
                    if uncertain_count
                    else "all submitted chapter groups accepted"
                    if run.status == run.Status.SUCCEEDED
                    else ""
                ),
            }
        )

    return render(
        request,
        "catalog/alignment_review.html",
        {
            "edition": edition,
            "chapter": chapter,
            "chapter_numbers": visible_chapter_numbers,
            "all_chapter_count": len(chapter_numbers),
            "chapter_nav": [
                {
                    "number": number,
                    "issue_count": (
                        len(warnings_by_chapter.get(number, [])) + coverage_gaps_by_chapter[number]
                    ),
                }
                for number in visible_chapter_numbers
            ],
            "view_filter": view_filter,
            "issue_chapter_count": len(issue_chapter_numbers),
            "chapter_mappings": chapter_mappings,
            "source_chapter_numbers": source_chapter_numbers,
            "alignment_groups": alignment_groups,
            "source_blocks": source_blocks,
            "target_blocks": target_blocks,
            "unmatched_source": [
                block for block in source_blocks if block.id not in aligned_source_ids
            ],
            "unmatched_target": [
                block for block in target_blocks if block.id not in aligned_target_ids
            ],
            "global_warnings": edition_level_warnings,
            "chapter_level_warnings": chapter_level_warnings,
            "chapter_warning_count": chapter_warning_count,
            "unresolved_warning_count": len(unresolved_warnings),
            "total_group_count": total_group_count,
            "ai_approved_count": ai_approved_count,
            "staff_approved_count": staff_approved_count,
            "pending_group_count": pending_group_count,
            "unmatched_source_count": unmatched_source_blocks.count(),
            "unmatched_target_count": unmatched_target_blocks.count(),
            "recent_revisions": edition.block_revisions.filter(
                block__chapter__sequence=chapter
            ).select_related("editor")[:10],
            "ai_run_summaries": ai_run_summaries,
            "ai_enabled": bool(settings.OPENAI_API_KEY),
        },
    )


def _review_redirect(edition_id: str, chapter: str, view_filter: str = "") -> HttpResponse:
    url = f"{reverse('catalog:alignment-review', args=[edition_id])}?chapter={chapter}"
    if view_filter == "issues":
        url += "&filter=issues"
    return redirect(url)


@staff_member_required
@require_POST
def queue_ai_alignment_review(request: HttpRequest, edition_id: str) -> HttpResponse:
    edition = get_object_or_404(Edition, id=edition_id, source_edition__isnull=False)
    if not settings.OPENAI_API_KEY:
        messages.error(request, "OPENAI_API_KEY is not configured for this service.")
    else:
        prepare_ai_alignment.delay(str(edition.id))
        messages.success(
            request,
            "Hierarchical alignment and OpenAI Batch review queued. "
            "The Batch window is up to 24 hours.",
        )
    return _review_redirect(
        str(edition.id), request.POST.get("chapter", "1"), request.POST.get("filter", "")
    )


@staff_member_required
@require_POST
def confirm_ai_safe_alignments(request: HttpRequest, edition_id: str) -> HttpResponse:
    edition = get_object_or_404(Edition, id=edition_id, source_edition__isnull=False)
    confirmed_count = confirm_ai_alignment_groups(edition=edition, reviewer=request.user)
    if confirmed_count:
        messages.success(request, f"Confirmed {confirmed_count} AI-approved alignment groups.")
    else:
        messages.info(request, "There are no unconfirmed AI-approved groups.")
    return _review_redirect(
        str(edition.id), request.POST.get("chapter", "1"), request.POST.get("filter", "")
    )


@staff_member_required
@require_POST
def accept_alignment_group(request: HttpRequest, edition_id: str, group_id: uuid.UUID):
    edition = get_object_or_404(Edition, id=edition_id, source_edition__isnull=False)
    try:
        review_alignment_group(
            edition=edition,
            group_id=group_id,
            reviewer=request.user,
            notes=request.POST.get("notes", "").strip(),
        )
    except ValueError as error:
        messages.error(request, str(error))
    else:
        messages.success(request, "Alignment group accepted and its warnings resolved.")
    return _review_redirect(
        str(edition.id), request.POST.get("chapter", "1"), request.POST.get("filter", "")
    )


@staff_member_required
@require_POST
def accept_alignment_chapter(request: HttpRequest, edition_id: str):
    edition = get_object_or_404(Edition, id=edition_id, source_edition__isnull=False)
    chapter = request.POST.get("chapter", "1")
    try:
        accepted_count = review_alignment_chapter(
            edition=edition,
            chapter=int(chapter),
            reviewer=request.user,
            notes=request.POST.get("notes", "").strip(),
        )
    except (TypeError, ValueError) as error:
        messages.error(request, str(error))
    else:
        messages.success(request, f"Accepted {accepted_count} alignment groups in chapter.")
    return _review_redirect(str(edition.id), chapter, request.POST.get("filter", ""))


@staff_member_required
@require_POST
def repair_alignment(request: HttpRequest, edition_id: str):
    edition = get_object_or_404(Edition, id=edition_id, source_edition__isnull=False)
    try:
        repair_alignment_group(
            edition=edition,
            source_block_ids=[uuid.UUID(value) for value in request.POST.getlist("source_blocks")],
            target_block_ids=[uuid.UUID(value) for value in request.POST.getlist("target_blocks")],
            reviewer=request.user,
            notes=request.POST.get("notes", "").strip(),
        )
    except (ValueError, TypeError) as error:
        messages.error(request, str(error))
    else:
        messages.success(request, "Manual alignment saved with an audit record.")
    return _review_redirect(
        str(edition.id), request.POST.get("chapter", "1"), request.POST.get("filter", "")
    )


@staff_member_required
@require_POST
def translate_alignment_gap(request: HttpRequest, edition_id: str, source_block_id: uuid.UUID):
    edition = get_object_or_404(Edition, id=edition_id, source_edition__isnull=False)
    chapter = request.POST.get("chapter", "1")
    try:
        translate_coverage_gap(
            edition=edition,
            source_block_id=source_block_id,
            target_chapter_sequence=int(chapter),
            translated_text=request.POST.get("text", ""),
            editor=request.user,
            notes=request.POST.get("notes", "").strip(),
        )
    except (TypeError, ValueError) as error:
        messages.error(request, str(error))
    else:
        messages.success(request, "Translation added and the coverage gap was aligned.")
    return _review_redirect(str(edition.id), chapter, request.POST.get("filter", ""))


@staff_member_required
@require_POST
def edit_alignment_target(request: HttpRequest, edition_id: str, block_id: uuid.UUID):
    edition = get_object_or_404(Edition, id=edition_id, source_edition__isnull=False)
    try:
        revise_block_text(
            edition=edition,
            block_id=block_id,
            revised_text=request.POST.get("text", ""),
            editor=request.user,
            notes=request.POST.get("notes", "").strip(),
        )
    except ValueError as error:
        messages.error(request, str(error))
    else:
        messages.success(request, "Target text updated; sentence splitting was queued.")
    return _review_redirect(
        str(edition.id), request.POST.get("chapter", "1"), request.POST.get("filter", "")
    )


@staff_member_required
@require_POST
def resolve_warning(request: HttpRequest, edition_id: str, warning_id: uuid.UUID):
    edition = get_object_or_404(Edition, id=edition_id)
    try:
        resolve_review_warning(edition=edition, warning_id=warning_id, reviewer=request.user)
    except ValueError as error:
        messages.error(request, str(error))
    else:
        messages.success(request, "Review item resolved.")
    if edition.source_edition_id:
        return _review_redirect(
            str(edition.id),
            request.POST.get("chapter", "1"),
            request.POST.get("filter", ""),
        )
    return redirect("catalog:edition-detail", edition_id=edition.id)


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
def retry_failed_edition(request: HttpRequest, edition_id: str) -> HttpResponse:
    edition = get_object_or_404(Edition.objects.select_related("work"), id=edition_id)
    if edition.status != Edition.Status.FAILED:
        messages.error(request, "Only failed editions can be retried.")
    elif edition.source_file:
        process_book_pipeline.delay(str(edition.id))
        messages.success(request, "Source reprocessing queued.")
    elif edition.blocks.exists():
        process_normalized_edition.delay(str(edition.id))
        messages.success(request, "Normalized content reprocessing queued.")
    elif (
        edition.parallel_role == Edition.ParallelRole.PARALLEL
        and edition.source_edition is not None
    ):
        # A parallel edition has no source file of its own; it is rebuilt by
        # translating its canonical source again.
        tier = last_translation_tier(edition)
        mode = last_translation_mode(edition)
        Edition.objects.filter(id=edition.id).update(
            status=Edition.Status.PROCESSING, updated_at=timezone.now()
        )
        if mode == "batch":
            prepare_translation.delay(str(edition.id), tier=tier)
        else:
            translate_edition_inline.delay(str(edition.id), tier)
        messages.success(request, f"Translation resubmitted on the {tier} tier ({mode}).")
    else:
        messages.error(request, "No source file or normalized content is available to retry.")
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
