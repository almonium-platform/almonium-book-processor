"""Move legacy illustration text out of the text stream without buying new work."""

from collections import Counter, defaultdict

from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from almonium_book_processor import __version__
from almonium_book_processor.catalog import chapter_analysis, chapter_projections
from almonium_book_processor.catalog.models import (
    ContentBlock,
    Edition,
    EditionArtifact,
    PipelineRun,
)
from almonium_book_processor.catalog.offline_sentence_alignment import _digest
from almonium_book_processor.catalog.parallel_content import inherited_pairs, pair_hash
from almonium_book_processor.catalog.tasks import _edition_content_hash, _text_hash
from almonium_book_processor.processing.sentence_correspondence import VERSION

REASON = "image_text_moved_to_metadata"


def _carry(run, key, digest, summary, *, cleanup="image_cleanup", reason=REASON, **provenance):
    carried, _ = PipelineRun.objects.get_or_create(
        idempotency_key=key,
        defaults={
            "edition_id": run.edition_id,
            "stage": run.stage,
            "processor_version": run.processor_version,
            "input_hash": digest,
            "status": PipelineRun.Status.SUCCEEDED,
            "progress": 100,
            "finished_at": timezone.now(),
            "summary": {
                **summary,
                cleanup: {"reason": reason, "from_run": str(run.pk), **provenance},
            },
        },
    )
    if carried.status != PipelineRun.Status.SUCCEEDED:
        raise ValueError("An unfinished run already claims the cleaned content.")
    return carried


def _sentence_hash(edition):
    return _text_hash(
        edition.source_sha256,
        edition.language,
        settings.NLP_SPACY_MODELS.get(edition.language, "blank"),
        _edition_content_hash(edition),
    )


def _alignment_runs(edition_ids):
    runs = PipelineRun.objects.filter(
        stage=PipelineRun.Stage.ALIGN,
        status=PipelineRun.Status.SUCCEEDED,
        summary__method=VERSION,
    ).filter(
        Q(edition_id__in=edition_ids) | Q(summary__secondary_id__in=[str(i) for i in edition_ids])
    )
    latest = {}
    for run in runs.order_by("-created_at", "-pk"):
        key = (run.edition_id, run.summary["secondary_id"], run.processor_version)
        latest.setdefault(key, run)
    return latest.values()


def _clean_alignment(run, primary, secondary, changed_ids):
    pairs = inherited_pairs(primary, secondary)
    if not pairs or _digest(pairs) != run.input_hash:
        return 0
    changes = []
    for left, right in pairs:
        if left.pk not in changed_ids and right.pk not in changed_ids:
            continue
        old = pair_hash(left, right)
        for block in (left, right):
            if block.pk in changed_ids:
                block.text, block.sentences = "", []
        if any(block.text or block.sentences for block in (left, right)):
            raise ValueError(
                f"{primary.slug} / {secondary.slug}: image is paired with readable text."
            )
        changes.append((left.chapter_id, old, pair_hash(left, right)))
    if not changes:
        return 0

    artifacts = EditionArtifact.objects.filter(
        edition=primary,
        kind=EditionArtifact.Kind.SENTENCE_ALIGNMENT,
        input_hash__in=[old for _, old, _ in changes],
        processor_version=run.processor_version,
    )
    prior = {row.input_hash: row.payload for row in artifacts.filter(is_current=True)}
    if len(prior) != len(changes):
        raise ValueError(f"{primary.slug} / {secondary.slug}: alignment history is incomplete.")

    summary = {key: value for key, value in run.summary.items() if key != "embedding"}
    reasons = Counter(summary.get("fallback_reasons", {}))
    for payload in prior.values():
        groups = payload["groups"]
        confirmed = sum(bool(g["certain"] and g["primary"] and g["secondary"]) for g in groups)
        summary["highlighted_groups"] -= confirmed
        summary["uncertain_groups"] -= sum(
            not g["certain"] and bool(g["primary"] and g["secondary"]) for g in groups
        )
        summary["paragraph_fallback_blocks"] += int(any(g["certain"] for g in groups))
        if not any(g["certain"] for g in groups):
            reasons[payload.get("fallback_reason", "low_confidence")] -= 1
        reasons["missing_sentences"] += 1
    summary["fallback_reasons"] = +reasons
    digest = _digest(pairs)
    carried = _carry(run, f"{run.processor_version}:{digest}", digest, summary)
    artifacts.update(is_current=False)
    for chapter_id, _, new in changes:
        EditionArtifact.objects.update_or_create(
            edition=primary,
            kind=EditionArtifact.Kind.SENTENCE_ALIGNMENT,
            input_hash=new,
            processor_version=run.processor_version,
            defaults={
                "chapter_id": chapter_id,
                "pipeline_run": carried,
                "payload": {
                    "groups": [],
                    "method": "paragraph_fallback",
                    "fallback_reason": "missing_sentences",
                    "model": summary["model"],
                },
                "is_current": True,
            },
        )
    return len(changes)


def _analysis_plan(edition, run):
    try:
        return chapter_analysis.snapshot(edition, run.summary["spec"])
    except (KeyError, ValueError):
        return None


def _carry_analysis(edition, run, before, *, cleanup="image_cleanup", reason=REASON):
    after = _analysis_plan(edition, run)
    if before is None or after is None or before["hash"] != run.input_hash:
        return "analysis already stale or unavailable"
    if after["hash"] == before["hash"]:
        return "analysis unchanged"
    chapters = {entry["id"] for entry in after["chapters"]}
    current = edition.artifacts.filter(kind__in=chapter_projections.KINDS, is_current=True)
    book = current.filter(chapter__isnull=True, payload__analysis_input_hash=before["hash"]).first()
    if book is None:
        return "analysis missing a current projection"
    old_hashes = {entry["id"]: entry["hash"] for entry in before["chapters"]}
    artifacts = [
        row
        for row in current.filter(chapter_id__in=chapters)
        if row.payload.get("chapter_hash") == old_hashes.get(str(row.chapter_id))
        and row.payload.get("analysis_spec_hash") == book.payload.get("analysis_spec_hash")
    ]
    expected = {(chapter, kind) for chapter in chapters for kind in chapter_projections.KINDS}
    if {(str(row.chapter_id), row.kind) for row in artifacts} != expected:
        return "analysis missing current chapter projections"
    digest = after["hash"]
    carried = _carry(
        run,
        f"{edition.pk}:chapter-analysis:{digest}",
        digest,
        run.summary,
        cleanup=cleanup,
        reason=reason,
        chapter_artifacts=[str(row.pk) for row in artifacts],
    )
    if carried.summary.get(cleanup, {}).get("from_run") != str(run.pk):
        return "cleaned analysis already available"
    chapter_projections.refresh_projections(str(carried.pk))
    return "analyses carried"


@transaction.atomic
def clean_image_text(*, apply=False, work=None):
    """All work is local. Roll back the same checks and writes when previewing."""
    images = ContentBlock.objects.filter(
        block_type=ContentBlock.BlockType.IMAGE, edition__withdrawal_requested_at=None
    ).exclude(text="")
    if work:
        images = images.filter(edition__work__slug=work)
    rows = list(images.select_for_update(of=("self",)).order_by("id"))
    grouped = defaultdict(list)
    for row in rows:
        grouped[row.edition_id].append(row)
    editions = list(Edition.objects.select_for_update().filter(pk__in=grouped).order_by("id"))
    stats = Counter({"image blocks": len(rows), "editions": len(editions)})
    if PipelineRun.objects.filter(
        edition__work_id__in={edition.work_id for edition in editions},
        status__in=(PipelineRun.Status.QUEUED, PipelineRun.Status.RUNNING),
    ).exists():
        raise ValueError("An affected work has a queued or running job.")
    changed_ids = {block.pk for block in rows}
    for run in _alignment_runs(grouped):
        primary, secondary = (
            Edition.objects.get(pk=pk) for pk in (run.edition_id, run.summary["secondary_id"])
        )
        count = _clean_alignment(run, primary, secondary, changed_ids)
        if count:
            stats["alignment runs carried"] += 1
            stats["image-only alignments"] += count
    for edition in editions:
        successful = edition.pipeline_runs.filter(status=PipelineRun.Status.SUCCEEDED)
        sentence = (
            successful.filter(stage=PipelineRun.Stage.SENTENCES)
            .filter(
                input_hash__in=[
                    _sentence_hash(edition),
                    _text_hash(
                        edition.source_sha256,
                        edition.language,
                        settings.NLP_SPACY_MODELS.get(edition.language, "blank"),
                    ),
                ]
            )
            .first()
        )
        analysis = successful.filter(stage=PipelineRun.Stage.CHAPTER_ANALYSIS).first()
        before = _analysis_plan(edition, analysis) if analysis else None
        for block in grouped[edition.pk]:
            if "legacy_image_text" in block.attributes:
                raise ValueError(
                    f"{edition.slug}: {block.block_id} already has archived image text."
                )
            block.attributes = {
                **block.attributes,
                "legacy_image_text": {"text": block.text, "sentences": block.sentences},
            }
            block.text, block.sentences = "", []
            block.updated_at = timezone.now()
        changed = grouped[edition.pk]
        ContentBlock.objects.bulk_update(changed, ["attributes", "text", "sentences", "updated_at"])
        blocks = list(edition.blocks.values_list("text", "sentences"))
        Edition.objects.filter(pk=edition.pk).update(
            word_count=sum(len(text.split()) for text, _ in blocks)
        )
        if sentence:
            digest = _sentence_hash(edition)
            _carry(
                sentence,
                f"{edition.pk}:{digest}:sentences:{__version__}",
                digest,
                {
                    **sentence.summary,
                    "blocks": sum(bool(text) for text, _ in blocks),
                    "sentences": sum(len(spans) for _, spans in blocks),
                },
            )
            stats["sentence runs carried"] += 1
        if analysis:
            stats[_carry_analysis(edition, analysis, before)] += 1
    if not apply:
        transaction.set_rollback(True)
    return stats
