"""What each parallel companion of an edition offers the reader right now.

Paragraph pairing is inherited from the canonical block groups and is either
complete or absent. Sentence highlights come from an offline embedding job per
pair, keyed by the text of both sides, so a correction on either side retires
them and the reader silently drops back to paragraph pairing. This module
measures that gap per pair and re-queues the job where one used to exist.
"""

import logging

from django.db.models import Q

from almonium_book_processor.catalog.models import Edition, EditionArtifact, PipelineRun
from almonium_book_processor.catalog.offline_sentence_alignment import (
    available_models,
    processor_version,
    queue_alignment,
)
from almonium_book_processor.catalog.parallel_content import inherited_pairs, pair_hash
from almonium_book_processor.processing.sentence_correspondence import VERSION

logger = logging.getLogger(__name__)

# Rendered as a status chip: the class the admin already uses for that mood.
BADGES = {
    "current": "succeeded",
    "running": "queued",
    "stale": "review",
    "failed": "failed",
    "missing": "missing",
    "incomplete": "failed",
}


def companions(edition):
    """The other editions this one can be read beside, canonical first."""

    if not edition.supports_parallel_reading:
        return []
    return list(
        Edition.objects.filter(
            work=edition.work,
            parallel_role__in=[Edition.ParallelRole.CANONICAL, Edition.ParallelRole.PARALLEL],
        )
        .exclude(id=edition.id)
        .order_by("parallel_role", "language", "cefr_level")
    )


def latest_run(edition, other):
    return (
        PipelineRun.objects.filter(stage=PipelineRun.Stage.ALIGN, summary__method=VERSION)
        .filter(
            Q(edition=edition, summary__secondary_id=str(other.id))
            | Q(edition=other, summary__secondary_id=str(edition.id))
        )
        .order_by("-created_at")
        .first()
    )


def pair_status(edition, other):
    pairs = inherited_pairs(edition, other)
    run = latest_run(edition, other)
    status = {
        "other": other,
        "total": len(pairs),
        "complete": bool(pairs),
        "current": 0,
        "reusable": 0,
        "changed": 0,
        "run": run,
        "model": (run.summary.get("model") if run else None),
        "state": "incomplete",
    }
    if not pairs:
        status["badge"] = BADGES[status["state"]]
        return status
    versions = [processor_version(model) for model in available_models()]
    digests = [(pair_hash(p, s), pair_hash(s, p)) for p, s in pairs]
    rows = EditionArtifact.objects.filter(
        kind=EditionArtifact.Kind.SENTENCE_ALIGNMENT,
        edition__in=[edition, other],
        processor_version__in=versions,
        input_hash__in=[digest for both in digests for digest in both],
    ).values_list("input_hash", "is_current")
    current_hashes = {digest for digest, is_current in rows if is_current}
    retired_hashes = {digest for digest, is_current in rows if not is_current}
    for forward, backward in digests:
        if forward in current_hashes or backward in current_hashes:
            status["current"] += 1
        elif forward in retired_hashes or backward in retired_hashes:
            # The text is unchanged: a re-run serves this block from cache.
            status["reusable"] += 1
        else:
            status["changed"] += 1
    if run and run.status in (PipelineRun.Status.QUEUED, PipelineRun.Status.RUNNING):
        status["state"] = "running"
    elif status["current"] == len(pairs):
        status["state"] = "current"
    elif run and run.status == PipelineRun.Status.FAILED:
        status["state"] = "failed"
    elif run is None and not rows:
        status["state"] = "missing"
    else:
        status["state"] = "stale"
    status["badge"] = BADGES[status["state"]]
    return status


def companion_rows(edition):
    return [pair_status(edition, other) for other in companions(edition)]


def refresh_sentence_alignment(edition):
    """Re-queue the offline sentence job for every companion pair that lost it.

    Only pairs that were aligned before are queued, in the orientation and
    with the model of their last run, so a correction never starts embedding
    work nobody asked for. Unchanged blocks are served from the retired cache.
    """

    queued = []
    for status in companion_rows(edition):
        if status["state"] not in {"stale", "failed"}:
            continue
        run = status["run"]
        primary_id, secondary_id = (
            (run.edition_id, run.summary["secondary_id"])
            if run
            else (edition.id, status["other"].id)
        )
        model = status["model"] if status["model"] in available_models() else None
        try:
            queued.append(queue_alignment(primary_id, secondary_id, model=model))
        except ValueError as error:
            logger.warning(
                "Could not refresh sentence alignment between %s and %s: %s",
                edition.slug,
                status["other"].slug,
                error,
            )
    return queued
