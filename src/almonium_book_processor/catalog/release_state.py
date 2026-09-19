"""Where a published edition stands against what readers are actually served.

Publication tells the product API an edition's metadata; the text itself is
read from this service live, so a correction here reaches this environment's
readers at once and only the metadata can fall behind. Other environments
never read from here: they hold the copy the last promotion bundle carried,
so every correction, artifact and review after that bundle is invisible there
until the edition is promoted again.
"""

from __future__ import annotations

from typing import Any

from django.db.models import Max

from almonium_book_processor.catalog.models import (
    ContentBlockRevision,
    Edition,
    EditionArtifact,
    PipelineRun,
)

LOCAL = "here"


def _since(editions, moment) -> dict[str, int]:
    return {
        "corrections": ContentBlockRevision.objects.filter(
            edition__in=editions, created_at__gt=moment
        ).count(),
        "artifacts": EditionArtifact.objects.filter(
            edition__in=editions, is_current=True, created_at__gt=moment
        ).count(),
    }


def release_rows(edition: Edition) -> list[dict[str, Any]]:
    """One row per place this edition has been released to, local first."""

    from almonium_book_processor.catalog.promotion import promotion_chain, promotion_targets
    from almonium_book_processor.catalog.tasks import publication_stale

    rows: list[dict[str, Any]] = []
    # The local row always exists: a publish that failed, or is still in the
    # queue, must be visible where the button that queued it stands, or the
    # editor sees "Update queued" and then nothing at all.
    publish_runs = list(
        edition.pipeline_runs.filter(stage=PipelineRun.Stage.PUBLISH).order_by("-created_at")
    )
    publish_pending = any(
        run.status in (PipelineRun.Status.QUEUED, PipelineRun.Status.RUNNING)
        for run in publish_runs
    )
    publish_failed = (
        publish_runs[0]
        if publish_runs and publish_runs[0].status == PipelineRun.Status.FAILED
        else None
    )
    if edition.status == Edition.Status.PUBLISHED and edition.published_at:
        behind = publication_stale(edition)
        changes = _since([edition], edition.published_at)
        rows.append(
            {
                "target": LOCAL,
                "state": "running" if publish_pending else "behind" if behind else "current",
                "at": edition.published_at,
                "metadata_behind": behind,
                "run": publish_failed,
                **changes,
            }
        )
    else:
        rows.append(
            {
                "target": LOCAL,
                "state": "running" if publish_pending else "unpublished",
                "at": None,
                "metadata_behind": False,
                "run": publish_failed,
                "corrections": 0,
                "artifacts": 0,
            }
        )
    promotions = edition.pipeline_runs.filter(stage=PipelineRun.Stage.PROMOTE).order_by(
        "-created_at"
    )
    names = [target.name for target in promotion_targets()]
    for run in promotions:
        name = run.summary.get("target")
        if name and name not in names:
            names.append(name)
    chain = promotion_chain(edition)
    for name in names:
        runs = [run for run in promotions if run.summary.get("target") == name]
        pending = any(
            run.status in (PipelineRun.Status.QUEUED, PipelineRun.Status.RUNNING) for run in runs
        )
        last = next((run for run in runs if run.status == PipelineRun.Status.SUCCEEDED), None)
        failed = runs[0] if runs and runs[0].status == PipelineRun.Status.FAILED else None
        if last is None:
            rows.append(
                {
                    "target": name,
                    "state": "running" if pending else "never",
                    "at": None,
                    "run": failed,
                    "corrections": 0,
                    "artifacts": 0,
                }
            )
            continue
        changes = _since(chain, last.created_at)
        rows.append(
            {
                "target": name,
                "state": (
                    "running"
                    if pending
                    else "behind"
                    if changes["corrections"] or changes["artifacts"]
                    else "current"
                ),
                "at": last.finished_at or last.created_at,
                "run": failed,
                "published_there": bool(last.summary.get("publish")),
                **changes,
            }
        )
    return rows


def behind_labels(editions) -> dict[Any, str]:
    """For a listing: which published editions are behind somewhere, in a few queries.

    Metadata is behind when no successful publish run carries the current
    publication key. A promotion target is behind when the edition or its
    source changed after the last successful bundle to that target. Only the
    direct source is checked here; the edition page walks the whole chain.
    """

    from almonium_book_processor.catalog.tasks import publication_input_hash

    editions = [e for e in editions if e.status == Edition.Status.PUBLISHED]
    if not editions:
        return {}
    ids = [e.id for e in editions]
    related = ids + [e.source_edition_id for e in editions if e.source_edition_id]
    published = {}
    for edition_id, digest in PipelineRun.objects.filter(
        edition_id__in=ids, stage=PipelineRun.Stage.PUBLISH, status=PipelineRun.Status.SUCCEEDED
    ).values_list("edition_id", "input_hash"):
        published.setdefault(edition_id, set()).add(digest)
    promoted: dict[Any, dict[str, Any]] = {}
    for run in (
        PipelineRun.objects.filter(
            edition_id__in=ids, stage=PipelineRun.Stage.PROMOTE, status=PipelineRun.Status.SUCCEEDED
        )
        .order_by("edition_id", "-created_at")
        .only("edition_id", "created_at", "summary")
    ):
        target = run.summary.get("target")
        if target:
            promoted.setdefault(run.edition_id, {}).setdefault(target, run.created_at)
    changed = {}
    for model, extra in (
        (ContentBlockRevision, {}),
        (EditionArtifact, {"is_current": True}),
    ):
        for row in (
            model.objects.filter(edition_id__in=related, **extra)
            .values("edition_id")
            .annotate(last=Max("created_at"))
        ):
            changed[row["edition_id"]] = max(
                changed.get(row["edition_id"], row["last"]), row["last"]
            )
    labels = {}
    for edition in editions:
        reasons = []
        digests = published.get(edition.id)
        if digests and publication_input_hash(edition) not in digests:
            reasons.append("metadata")
        latest = max(
            (
                moment
                for moment in (changed.get(edition.id), changed.get(edition.source_edition_id))
                if moment
            ),
            default=None,
        )
        for target, moment in promoted.get(edition.id, {}).items():
            if latest and latest > moment:
                reasons.append(target)
        if reasons:
            labels[edition.id] = ", ".join(reasons)
    return labels
