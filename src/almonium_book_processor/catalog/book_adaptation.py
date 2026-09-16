"""Complete B2 editions: checkpointed generation, atomic materialization, no publication."""

from concurrent.futures import ThreadPoolExecutor

from django.conf import settings
from django.db import close_old_connections, transaction
from django.utils import timezone

from almonium_book_processor.ai.adaptation import PROMPT_VERSION, SYSTEM_PROMPT, ChapterAdaptation
from almonium_book_processor.catalog.adaptation import (
    MAX_BLOCKS,
    MAX_CHARS,
    digest,
    queue_pilot,
    run_pilot,
)
from almonium_book_processor.catalog.ai_translation import _unique_slug
from almonium_book_processor.catalog.models import (
    Chapter,
    ContentBlock,
    Edition,
    PipelineRun,
    QAWarning,
    Work,
)

VERSION = "b2-book-v1"
WORKERS = 3
REVIEW_CODE = "adaptation_fidelity_review"


def generation_spec():
    return {
        "processor": VERSION,
        "model": settings.OPENAI_TRANSLATION_QUALITY_MODEL,
        "prompt_version": PROMPT_VERSION,
        "prompt_hash": digest(SYSTEM_PROMPT),
        "schema_hash": digest(ChapterAdaptation.model_json_schema()),
    }


def book_plan(source):
    if source.work.visibility != Work.Visibility.PUBLIC or source.withdrawal_requested_at:
        raise ValueError("Choose an available public source edition.")
    if not source.supports_parallel_reading:
        raise ValueError("The source must have canonical block correspondence.")
    chapters, windows, signature = [], [], []
    count = 0
    for chapter in source.chapters.order_by("sequence").prefetch_related("blocks"):
        blocks = sorted(chapter.blocks.all(), key=lambda b: b.sequence)
        chapters.append(
            {
                "id": str(chapter.id),
                "sequence": chapter.sequence,
                "title": chapter.title,
                "role": chapter.analysis_role,
            }
        )
        signature.append(
            [
                chapters[-1],
                [
                    [b.block_id, b.sequence, b.block_type, b.text, str(b.align_group), b.attributes]
                    for b in blocks
                ],
            ]
        )
        chunk, chars = [], 0
        for block in blocks:
            if not block.align_group:
                raise ValueError("Every source block must have a canonical alignment group.")
            if len(block.text) > MAX_CHARS:
                raise ValueError(f"Block {block.block_id} exceeds the generation window limit.")
            if chunk and (chars + len(block.text) > MAX_CHARS or len(chunk) >= MAX_BLOCKS):
                windows.append({"chapter_id": str(chapter.id), "block_ids": chunk})
                chunk, chars = [], 0
            chunk.append(block.block_id)
            chars += len(block.text)
            count += 1
        if chunk:
            windows.append({"chapter_id": str(chapter.id), "block_ids": chunk})
    if not count:
        raise ValueError("The source has no normalized blocks.")
    # No timestamps: sentence enrichment does not invalidate the generation source.
    source_hash = digest(
        [
            source.source_sha256,
            source.language,
            source.title,
            source.author,
            source.work.title,
            signature,
        ]
    )
    return {"chapters": chapters, "windows": windows, "blocks": count, "source_hash": source_hash}


@transaction.atomic
def queue_book(source_id):
    from almonium_book_processor.catalog.tasks import adapt_book

    if not settings.OPENAI_API_KEY:
        raise ValueError("Configure an OpenAI key to generate an adaptation.")
    source = Edition.objects.select_for_update().select_related("work").get(pk=source_id)
    plan = book_plan(source)
    spec = generation_spec()
    input_hash = digest([plan, spec])
    key = f"{source.id}:b2-book:{input_hash}"
    run = PipelineRun.objects.filter(idempotency_key=key).select_related("edition").first()
    if run is None:
        edition = Edition.objects.create(
            work=source.work,
            source_edition=source,
            slug=_unique_slug(f"{source.slug[:155]}-b2"),
            title=f"{source.title[:480]} — B2 adaptation",
            author=source.author,
            language=source.language,
            edition_type=Edition.EditionType.ADAPTATION,
            parallel_role=Edition.ParallelRole.PARALLEL,
            status=Edition.Status.QUEUED,
            auto_publish=False,
            # Target is in the run, not passed off as an assessed editorial level.
            cefr_level=None,
        )
        run = PipelineRun.objects.create(
            edition=edition,
            stage=PipelineRun.Stage.ADAPT,
            processor_version=VERSION,
            input_hash=input_hash,
            idempotency_key=key,
            summary={"plan": plan, "spec": spec, "target_level": "B2", "completed": 0},
        )
    if run.status in {PipelineRun.Status.SUCCEEDED, PipelineRun.Status.RUNNING}:
        return run
    if run.edition.blocks.exists():
        raise ValueError("This edition already contains text; do not overwrite reviewed content.")
    run.status = PipelineRun.Status.QUEUED
    run.error = ""
    run.finished_at = None
    run.save(update_fields=["status", "error", "finished_at", "updated_at"])
    Edition.objects.filter(pk=run.edition_id).update(status=Edition.Status.QUEUED)
    transaction.on_commit(lambda: adapt_book.delay(str(run.id)))
    return run


def _generate(child_id):
    close_old_connections()
    try:
        run_pilot(child_id)
    finally:
        close_old_connections()


def run_book(run_id, *, provider=None):
    if not PipelineRun.objects.filter(pk=run_id, status=PipelineRun.Status.QUEUED).update(
        status=PipelineRun.Status.RUNNING, started_at=timezone.now(), progress=1
    ):
        return
    run = PipelineRun.objects.select_related("edition__source_edition__work").get(pk=run_id)
    source = run.edition.source_edition
    plan = run.summary["plan"]
    Edition.objects.filter(pk=run.edition_id).update(status=Edition.Status.PROCESSING)
    try:
        if generation_spec() != run.summary["spec"]:
            raise ValueError(
                "Generation configuration changed; start a new version from the source."
            )
        results = {}
        total = len(plan["windows"])
        # At most three paid requests in flight; stop launching batches after any failure.
        for start in range(0, total, WORKERS):
            source.refresh_from_db()
            if book_plan(source)["source_hash"] != plan["source_hash"]:
                raise ValueError(
                    "Source changed; saved results retained, edition not materialized."
                )
            children = []
            for window in plan["windows"][start : start + WORKERS]:
                chapter = source.chapters.get(pk=window["chapter_id"])
                blocks = list(chapter.blocks.filter(block_id__in=window["block_ids"]))
                if not any(b.text.strip() for b in blocks):
                    for block in blocks:
                        results[block.block_id] = {
                            "text": block.text,
                            "decision": "kept",
                            "reason": "",
                            "ai_run_id": None,
                        }
                    continue
                child = queue_pilot(
                    source.id,
                    chapter.id,
                    target_edition_id=run.edition_id,
                    block_ids=window["block_ids"],
                    dispatch=False,
                )
                children.append(child)
            if provider is not None:
                # Fake providers stay on the test DB connection; CI never calls the network.
                for child in children:
                    run_pilot(child.id, provider=provider)
            else:
                with ThreadPoolExecutor(max_workers=WORKERS) as pool:
                    list(pool.map(_generate, [child.id for child in children]))
            for child in children:
                child.refresh_from_db()
                if child.status != PipelineRun.Status.SUCCEEDED:
                    raise ValueError("A chapter is still running; reconcile it before retrying.")
                ai = child.ai_runs.get(pk=child.summary["ai_run_id"])
                for block in ai.response_payload["adaptation"]["blocks"]:
                    results[block["block_id"]] = {**block, "ai_run_id": str(ai.id)}
            completed = min(start + WORKERS, total)
            run.summary = {**run.summary, "completed": completed}
            run.progress = max(1, int(90 * completed / total))
            run.save(update_fields=["summary", "progress", "updated_at"])
        _materialize(run, results)
    except Exception as error:
        PipelineRun.objects.filter(pk=run_id).update(
            status=PipelineRun.Status.FAILED, error=str(error)[:1000], finished_at=timezone.now()
        )
        Edition.objects.filter(pk=run.edition_id).exclude(status=Edition.Status.PUBLISHED).update(
            status=Edition.Status.FAILED
        )
        raise


@transaction.atomic
def _materialize(run, results):
    from almonium_book_processor.catalog.tasks import _alignment_input_hash, enrich_adapted_book

    # Source-first lock order matches queue_pilot. Never overwrite source or a prior result.
    source = (
        Edition.objects.select_for_update()
        .select_related("work")
        .get(pk=run.edition.source_edition_id)
    )
    target = Edition.objects.select_for_update().get(pk=run.edition_id)
    plan = run.summary["plan"]
    if book_plan(source)["source_hash"] != plan["source_hash"]:
        raise ValueError("Source changed before materialization.")
    if (
        target.blocks.exists()
        or target.status == Edition.Status.PUBLISHED
        or target.withdrawal_requested_at
    ):
        raise ValueError("Target changed; refusing to overwrite it.")
    source_blocks = list(
        source.blocks.select_related("chapter").order_by("chapter__sequence", "sequence")
    )
    if set(results) != {b.block_id for b in source_blocks}:
        raise ValueError(
            "Incomplete output: every source block is required before materialization."
        )
    chapters = {}
    for entry in plan["chapters"]:
        chapters[entry["id"]] = Chapter.objects.create(
            edition=target,
            sequence=entry["sequence"],
            title=entry["title"],
            analysis_role=entry["role"],
        )
    rows = []
    for block in source_blocks:
        adapted = results[block.block_id]
        rows.append(
            ContentBlock(
                edition=target,
                chapter=chapters[str(block.chapter_id)],
                block_id=block.block_id,
                sequence=block.sequence,
                block_type=block.block_type,
                text=adapted["text"],
                align_group=block.align_group,
                source_ref=f"{source.slug}:{block.block_id}",
                attributes={
                    **block.attributes,
                    "adaptation": {
                        "source_revision": plan["source_hash"],
                        "target_level": "B2",
                        "decision": adapted["decision"],
                        "reason": adapted["reason"],
                        "ai_run_id": adapted["ai_run_id"],
                        "prompt_version": run.summary["spec"]["prompt_version"],
                    },
                },
            )
        )
    ContentBlock.objects.bulk_create(rows, batch_size=1000)
    target.source_sha256 = digest([[b.block_id, b.text] for b in rows])
    target.word_count = sum(len(b.text.split()) for b in rows)
    target.status = Edition.Status.REVIEW
    target.auto_publish = False
    target.save(
        update_fields=["source_sha256", "word_count", "status", "auto_publish", "updated_at"]
    )
    alignment_hash = _alignment_input_hash(source, target)
    PipelineRun.objects.create(
        edition=target,
        stage=PipelineRun.Stage.ALIGN,
        processor_version=VERSION,
        input_hash=alignment_hash,
        idempotency_key=f"{target.id}:inherited:{alignment_hash}",
        status=PipelineRun.Status.SUCCEEDED,
        progress=100,
        finished_at=timezone.now(),
        summary={"strategy": "inherited_block_groups", "blocks": len(rows)},
    )
    QAWarning.objects.create(
        edition=target,
        pipeline_run=run,
        code=REVIEW_CODE,
        severity=QAWarning.Severity.WARNING,
        message="AI B2 adaptation: review fidelity, literary voice and achieved difficulty. "
        "B2 is the target, not a verified level. Source defects may remain. "
        "Inspect chapter change reasons and warnings before accepting this edition.",
    )
    run.status = PipelineRun.Status.SUCCEEDED
    run.progress = 100
    run.finished_at = timezone.now()
    run.summary = {
        **run.summary,
        "blocks": len(rows),
        "kept": sum(b.attributes["adaptation"]["decision"] == "kept" for b in rows),
        "review_required": True,
    }
    run.save()
    transaction.on_commit(lambda: enrich_adapted_book.delay(str(target.id)))
