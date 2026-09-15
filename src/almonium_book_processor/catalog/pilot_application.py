"""Apply one reviewed whole-chapter pilot without replacing editions or block IDs."""

from django.db import transaction

from almonium_book_processor.catalog.adaptation import digest, source_snapshot
from almonium_book_processor.catalog.chapter_analysis import analysis_spec
from almonium_book_processor.catalog.chapter_projections import LEVELS
from almonium_book_processor.catalog.models import (
    AIRun,
    Chapter,
    ContentBlock,
    Edition,
    PipelineRun,
    QAWarning,
)
from almonium_book_processor.catalog.services import _finish_text_revision, _record_block_revision


def chapter_revision(chapter):
    return digest(
        [
            [str(b.id), b.block_id, b.text, str(b.align_group), b.attributes]
            for b in chapter.blocks.order_by("sequence")
        ]
    )


@transaction.atomic
def apply_pilot(*, pilot_id, target_id, expected_revision, editor, notes):
    if not notes.strip():
        raise ValueError("Record your fidelity review before applying a chapter.")
    run = PipelineRun.objects.select_related("edition__work").get(pk=pilot_id)
    if run.processor_version != "b2-chapter-pilot-v1" or run.status != "succeeded":
        raise ValueError("Choose a completed standalone pilot.")
    if run.summary.get("block_ids") is not None:
        raise ValueError("Only whole-chapter pilots can replace a chapter.")
    source = run.edition
    target = Edition.objects.get(pk=target_id)
    if (
        source.work.visibility != "public"
        or target.work_id != source.work_id
        or target.source_edition_id != source.id
        or target.edition_type != "adaptation"
        or target.language != source.language
    ):
        raise ValueError("Choose a same-language adaptation derived directly from this source.")
    chapter = source.chapters.get(pk=run.summary["chapter_id"])
    target_chapter = target.chapters.get(sequence=chapter.sequence)
    list(
        ContentBlock.objects.select_for_update()
        .filter(chapter_id__in=[chapter.id, target_chapter.id])
        .order_by("id")
    )
    list(Edition.objects.select_for_update().filter(pk__in=[source.id, target.id]).order_by("id"))
    source.refresh_from_db()
    target.refresh_from_db()
    list(
        Chapter.objects.select_for_update()
        .filter(pk__in=[chapter.id, target_chapter.id])
        .order_by("id")
    )
    chapter.refresh_from_db()
    target_chapter.refresh_from_db()
    if (
        source.work.visibility != "public"
        or target.work_id != source.work_id
        or target.source_edition_id != source.id
        or target.edition_type != "adaptation"
        or target.language != source.language
        or target_chapter.sequence != chapter.sequence
    ):
        raise ValueError("Edition lineage or chapter metadata changed. Reload the preview.")
    if (
        source.withdrawal_requested_at
        or target.withdrawal_requested_at
        or target.status not in {"draft", "review", "ready"}
    ):
        raise ValueError("Only an unpublished, inactive adaptation can be changed.")
    if target.pipeline_runs.filter(status__in=["queued", "running"]).exists():
        raise ValueError("Wait for the adaptation's active jobs to finish.")
    targets = set(target.blocks.values_list("attributes__adaptation__target_level", flat=True))
    if targets != {"B2"}:
        raise ValueError("The target edition must consistently request B2 adaptation.")
    if chapter_revision(target_chapter) != expected_revision:
        raise ValueError("The target chapter changed. Reload and review it before applying.")
    if digest(source_snapshot(chapter)) != run.summary["source_hash"]:
        raise ValueError("The source chapter changed. Generate a current pilot.")
    assessment = source.pipeline_runs.filter(
        processor_version="pilot-difficulty-v1",
        status="succeeded",
        summary__pilot_id=str(run.id),
        summary__spec=analysis_spec(),
    ).first()
    level = assessment.summary.get("assessment", {}).get("max_level") if assessment else None
    if level not in LEVELS or LEVELS.index(level) > LEVELS.index("B2"):
        raise ValueError("The pilot needs a current, complete assessment at or below B2.")
    generation = AIRun.objects.get(pk=run.summary["ai_run_id"], edition=source, status="succeeded")
    originals = list(chapter.blocks.order_by("sequence"))
    targets = list(target_chapter.blocks.order_by("sequence"))
    output = generation.response_payload["adaptation"]["blocks"]
    if (
        [b.block_id for b in originals] != [b.block_id for b in targets]
        or [b.block_id for b in targets] != [b["block_id"] for b in output]
        or any(
            not s.align_group or s.align_group != t.align_group or s.block_type != t.block_type
            for s, t in zip(originals, targets, strict=True)
        )
    ):
        raise ValueError("Chapter block identities, types and inherited groups must match exactly.")
    changed = set()
    for block, result in zip(targets, output, strict=True):
        if block.text == result["text"].strip():
            continue
        _record_block_revision(
            edition=target,
            block=block,
            revised_text=result["text"],
            editor=editor,
            notes=f"Applied pilot {run.id}; generation {generation.id}; "
            f"previous adaptation metadata: {block.attributes.get('adaptation', {})}. "
            f"Fidelity review: {notes.strip()}",
        )
        block.attributes = {
            **block.attributes,
            "adaptation": {
                **block.attributes.get("adaptation", {}),
                "target_level": "B2",
                "decision": result["decision"],
                "reason": result["reason"],
                "ai_run_id": str(generation.id),
                "prompt_version": generation.prompt_template.version,
                "applied_pilot_id": str(run.id),
            },
        }
        block.save(update_fields=["attributes", "updated_at"])
        changed.add(block.id)
    if not changed:
        return 0
    target.status = Edition.Status.REVIEW
    target.auto_publish = False
    target.save(update_fields=["status", "auto_publish", "updated_at"])
    QAWarning.objects.create(
        edition=target,
        code="adaptation_chapter_replaced",
        severity="warning",
        message=f"Chapter {chapter.sequence} replaced from pilot {run.id}. "
        "Check the complete edition and refreshed difficulty before completing review. "
        f"Recorded review: {notes.strip()}",
    )
    _finish_text_revision(target, changed)
    from almonium_book_processor.catalog.tasks import reassess_applied_pilot

    transaction.on_commit(lambda: reassess_applied_pilot.delay(str(target.id)))
    return len(changed)
