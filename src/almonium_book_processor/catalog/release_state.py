"""Where a published edition stands against what readers are actually served.

Publication tells the product API an edition's metadata; the text itself is
read from this service live, so a correction here reaches this environment's
readers at once and only the metadata can fall behind. Other environments
never read from here: they hold the copy the last promotion bundle carried,
so every correction, artifact and review after that bundle is invisible there
until the edition is promoted again.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from django.db.models import Max
from django.utils import timezone

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


@dataclass
class PromotionToken:
    """One environment's word on one edition, as the catalogue row shows it.

    The state is read off the latest promotion run to that target against the
    edition's last content change: ``current`` when nothing changed since a
    successful bundle, ``behind`` when something did, ``failed`` when the last
    attempt did not land, ``queued`` while one is in the queue or running, and
    ``never`` when nothing has gone there yet.
    """

    target: str
    state: str
    at: datetime | None = None
    error: str = ""

    @property
    def label(self) -> str:
        if self.state in ("behind", "failed", "queued"):
            return f"{self.target} {self.state}"
        return self.target

    @property
    def title(self) -> str:
        """What the release panel would say, for a hover over the token."""

        when = f" {timezone.localtime(self.at):%-d %b %H:%M}" if self.at else ""
        if self.state == "current":
            return f"Promoted to {self.target}{when} · current there. Nothing to do."
        if self.state == "behind":
            return f"Promoted to {self.target}{when} · changed since. Promote again."
        if self.state == "failed":
            error = f": {self.error}" if self.error else "."
            return f"The last promotion to {self.target} failed{error} Promote again."
        if self.state == "queued":
            return f"Promotion to {self.target} is running. Wait for it to land."
        return f"Never promoted to {self.target}."


@dataclass
class ListingReleaseState:
    """What a catalogue row shows about where its edition has been released."""

    metadata_behind: bool = False
    tokens: list[PromotionToken] = field(default_factory=list)


def listing_release_state(editions) -> dict[Any, ListingReleaseState]:
    """Where each listed edition stands, in a few queries for the whole list.

    Metadata is behind when no successful publish run carries the current
    publication key. A promotion token exists for every configured target,
    and for any target an edition has ever been promoted to, on every edition
    that is approved (ready or published) or has a promotion run: before
    approval there is nothing to promote and a token would only suggest
    otherwise. A target is behind when the edition or its source changed after
    the last successful bundle to it. Only the direct source is checked here;
    the edition page walks the whole chain.
    """

    from almonium_book_processor.catalog.promotion import promotion_targets
    from almonium_book_processor.catalog.tasks import publication_input_hash

    editions = list(editions)
    if not editions:
        return {}
    ids = [e.id for e in editions]
    published_ids = [e.id for e in editions if e.status == Edition.Status.PUBLISHED]
    related = ids + [e.source_edition_id for e in editions if e.source_edition_id]
    published: dict[Any, set[str]] = {}
    if published_ids:
        for edition_id, digest in PipelineRun.objects.filter(
            edition_id__in=published_ids,
            stage=PipelineRun.Stage.PUBLISH,
            status=PipelineRun.Status.SUCCEEDED,
        ).values_list("edition_id", "input_hash"):
            published.setdefault(edition_id, set()).add(digest)
    # Newest first per edition and target: the first run seen decides failed
    # or queued, the first successful one is what the target holds.
    runs: dict[Any, dict[str, list[PipelineRun]]] = {}
    for run in (
        PipelineRun.objects.filter(edition_id__in=ids, stage=PipelineRun.Stage.PROMOTE)
        .exclude(status=PipelineRun.Status.CANCELLED)
        .order_by("-created_at")
        .only("edition_id", "status", "created_at", "finished_at", "summary", "error")
    ):
        target = run.summary.get("target")
        if target:
            runs.setdefault(run.edition_id, {}).setdefault(target, []).append(run)
    configured = [target.name for target in promotion_targets()]
    changed: dict[Any, datetime] = {}
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
    states: dict[Any, ListingReleaseState] = {}
    for edition in editions:
        state = ListingReleaseState()
        digests = published.get(edition.id)
        if digests and publication_input_hash(edition) not in digests:
            state.metadata_behind = True
        by_target = runs.get(edition.id, {})
        approved = edition.status in (Edition.Status.READY, Edition.Status.PUBLISHED)
        if approved or by_target:
            names = configured + [name for name in by_target if name not in configured]
            for name in names:
                state.tokens.append(_token(edition, name, by_target.get(name, []), changed))
        states[edition.id] = state
    return states


def _token(edition, target, runs, changed) -> PromotionToken:
    if runs and runs[0].status in (PipelineRun.Status.QUEUED, PipelineRun.Status.RUNNING):
        return PromotionToken(target=target, state="queued")
    if runs and runs[0].status == PipelineRun.Status.FAILED:
        return PromotionToken(target=target, state="failed", error=runs[0].error)
    last = next((run for run in runs if run.status == PipelineRun.Status.SUCCEEDED), None)
    if last is None:
        return PromotionToken(target=target, state="never")
    latest = max(
        (
            moment
            for moment in (changed.get(edition.id), changed.get(edition.source_edition_id))
            if moment
        ),
        default=None,
    )
    state = "behind" if latest and latest > last.created_at else "current"
    return PromotionToken(target=target, state=state, at=last.finished_at or last.created_at)


def editions_to_promote(target: str, *, include_never: bool = True) -> list[Edition]:
    """Every public edition to send to ``target``, sources first.

    Includes editions that are behind or last failed on ``target`` and, when
    ``include_never`` is True, ready/published editions never promoted there yet.
    Editions blocked by ``promotion_blocker`` (e.g. still in review) are left out.
    """

    from almonium_book_processor.catalog.catalogue import _editions
    from almonium_book_processor.catalog.models import Work
    from almonium_book_processor.catalog.promotion import promotion_blocker, promotion_chain

    wanted = ("never", "behind", "failed") if include_never else ("behind", "failed")
    editions = list(_editions(Work.Visibility.PUBLIC))
    states = listing_release_state(editions)
    selected = [
        edition
        for edition in editions
        if any(
            token.target == target and token.state in wanted for token in states[edition.id].tokens
        )
        and not promotion_blocker(edition)
    ]
    return sorted(selected, key=lambda edition: (len(promotion_chain(edition)), edition.slug))


def editions_behind(target: str) -> list[Edition]:
    """Every public edition the target is behind on or last failed for, sources first."""

    return editions_to_promote(target, include_never=False)


def queue_promotions(
    target, editions: list[Edition], *, publish_new: bool = True
) -> list[PipelineRun]:
    """Queue one promotion per edition.

    Editions previously sent to ``target`` repeat what their last attempt asked
    for ``publish``; never-promoted editions use ``publish_new`` (True by default).
    """

    from almonium_book_processor import __version__
    from almonium_book_processor.catalog.tasks import promote_edition

    runs: list[PipelineRun] = []
    for edition in editions:
        last = (
            edition.pipeline_runs.filter(
                stage=PipelineRun.Stage.PROMOTE, summary__target=target.name
            )
            .order_by("-created_at")
            .first()
        )
        publish = bool(last.summary.get("publish")) if last is not None else publish_new
        run = PipelineRun.objects.create(
            edition=edition,
            stage=PipelineRun.Stage.PROMOTE,
            processor_version=__version__,
            input_hash="",
            idempotency_key=f"{edition.id}:promote:{target.name}:{uuid.uuid4().hex}",
            summary={"target": target.name, "target_url": target.base_url, "publish": publish},
        )
        promote_edition.delay(str(run.id), publish=publish)
        runs.append(run)
    return runs


def queue_promotions_behind(target, editions: list[Edition]) -> list[PipelineRun]:
    """Queue one promotion per behind/failed edition, repeating its last publish choice."""

    return queue_promotions(target, editions, publish_new=False)


def _local_changed_at(editions: list[Edition]) -> dict[Any, datetime]:
    """Latest change timestamp per edition (edition update, text revision, or current artifact)."""

    ids = [edition.id for edition in editions]
    changed: dict[Any, datetime] = {edition.id: edition.updated_at for edition in editions}
    if not ids:
        return changed
    for model, extra in (
        (ContentBlockRevision, {}),
        (EditionArtifact, {"is_current": True}),
    ):
        for row in (
            model.objects.filter(edition_id__in=ids, **extra)
            .values("edition_id")
            .annotate(last=Max("created_at"))
        ):
            if row["last"] and (
                row["edition_id"] not in changed or row["last"] > changed[row["edition_id"]]
            ):
                changed[row["edition_id"]] = row["last"]
    return changed


def check_target_sync(target) -> dict[str, Any]:
    """Ask ``target`` what reviewed editions it holds and report anything to pull first."""

    from django.utils.dateparse import parse_datetime

    from almonium_book_processor.catalog.promotion import (
        PromotionError,
        source_compatibility_problem,
    )
    from almonium_book_processor.catalog.promotion_client import PromotionClient

    checked_at = timezone.now().isoformat()
    try:
        listing = PromotionClient(target).exports()
    except PromotionError as error:
        return {"checked_at": checked_at, "error": str(error)}
    problem = source_compatibility_problem(listing)
    if problem:
        return {"checked_at": checked_at, "error": problem}

    remote_entries = listing.get("editions") or []
    local_editions = list(
        Edition.objects.all().only("id", "slug", "updated_at", "source_edition_id")
    )
    by_slug = {edition.slug: edition for edition in local_editions}
    by_id = {str(edition.id): edition for edition in local_editions}
    parent_of = {edition.id: edition.source_edition_id for edition in local_editions}
    local_changed = _local_changed_at(local_editions)

    # Pushing a derived edition carries its source chain in the same bundle, so
    # credit the push timestamp to the edition and every ancestor in its chain.
    last_pushed: dict[Any, datetime] = {}
    for run in (
        PipelineRun.objects.filter(
            stage=PipelineRun.Stage.PROMOTE,
            status=PipelineRun.Status.SUCCEEDED,
            summary__target=target.name,
        )
        .order_by("-created_at")
        .only("edition_id", "created_at", "finished_at")
    ):
        moment = run.finished_at or run.created_at
        cursor = run.edition_id
        seen: set[Any] = set()
        while cursor and cursor not in seen:
            seen.add(cursor)
            if cursor not in last_pushed or moment > last_pushed[cursor]:
                last_pushed[cursor] = moment
            cursor = parent_of.get(cursor)

    only_on_target: list[dict[str, str]] = []
    newer_on_target: list[dict[str, str]] = []
    supports_changed_at = any("changed_at" in entry for entry in remote_entries)
    for entry in remote_entries:
        slug = entry.get("slug", "")
        local = by_slug.get(slug) or by_id.get(entry.get("id", ""))
        if local is None:
            only_on_target.append({"slug": slug, "status": entry.get("status", "")})
            continue
        raw_changed = entry.get("changed_at")
        if raw_changed:
            remote_dt = parse_datetime(raw_changed)
            local_dt = local_changed.get(local.id)
            pushed_dt = last_pushed.get(local.id)
            baseline = max(
                (dt for dt in (local_dt, pushed_dt) if dt is not None),
                default=None,
            )
            # Small 5-second tolerance so a bundle we just pushed is not flagged as newer.
            if remote_dt and (baseline is None or remote_dt > baseline + timedelta(seconds=5)):
                newer_on_target.append({"slug": slug, "changed_at": raw_changed})

    pull_set = {item["slug"] for item in only_on_target} | {
        item["slug"] for item in newer_on_target
    }
    # Pull leaf editions whose bundles carry their sources, plus any standalone/changed ones.
    remote_sources = {
        entry.get("source_edition")
        for entry in remote_entries
        if entry.get("slug") in pull_set and entry.get("source_edition")
    }
    pull_slugs = sorted(slug for slug in pull_set if slug not in remote_sources)
    return {
        "checked_at": checked_at,
        "error": "",
        "remote_count": len(remote_entries),
        "only_on_target": sorted(only_on_target, key=lambda item: item["slug"]),
        "newer_on_target": sorted(newer_on_target, key=lambda item: item["slug"]),
        "pull_slugs": pull_slugs,
        "supports_changed_at": supports_changed_at,
    }


def promotion_sync_summary(remote_checks: dict[str, dict] | None = None) -> list[dict[str, Any]]:
    """Per-target promotion counts (new, behind, failed, queued) plus any cached remote check."""

    from almonium_book_processor.catalog.catalogue import _editions
    from almonium_book_processor.catalog.models import Work
    from almonium_book_processor.catalog.promotion import promotion_blocker, promotion_targets

    targets = promotion_targets()
    if not targets:
        return []
    editions = list(_editions(Work.Visibility.PUBLIC))
    states = listing_release_state(editions)
    remote_checks = remote_checks or {}
    rows: list[dict[str, Any]] = []
    for target in targets:
        new_count = behind_count = failed_count = queued_count = 0
        for edition in editions:
            token = next(
                (item for item in states[edition.id].tokens if item.target == target.name), None
            )
            if token is None:
                continue
            if token.state == "queued":
                queued_count += 1
            elif token.state == "never" and not promotion_blocker(edition):
                new_count += 1
            elif token.state == "behind" and not promotion_blocker(edition):
                behind_count += 1
            elif token.state == "failed" and not promotion_blocker(edition):
                failed_count += 1
        total = new_count + behind_count + failed_count
        behind_total = behind_count + failed_count
        remote = remote_checks.get(target.name)
        pull_count = (
            len(remote.get("only_on_target", [])) + len(remote.get("newer_on_target", []))
            if remote and not remote.get("error")
            else 0
        )
        rows.append(
            {
                "target": target.name,
                "new": new_count,
                "behind": behind_count,
                "failed": failed_count,
                "behind_total": behind_total,
                "queued": queued_count,
                "total": total,
                "remote": remote,
                "pull_count": pull_count,
            }
        )
    return rows


def editions_to_publish() -> list[Edition]:
    """Every public ready edition (and published edition with stale metadata) ready to publish here,
    in source-first order, skipping anything already queued/running for publication.
    """

    from almonium_book_processor.catalog.catalogue import _editions
    from almonium_book_processor.catalog.models import Work
    from almonium_book_processor.catalog.promotion import promotion_chain
    from almonium_book_processor.catalog.tasks import publication_blocker, publication_stale

    editions = list(_editions(Work.Visibility.PUBLIC))
    in_flight = set(
        PipelineRun.objects.filter(
            stage=PipelineRun.Stage.PUBLISH,
            status__in=[PipelineRun.Status.QUEUED, PipelineRun.Status.RUNNING],
            edition__work__visibility=Work.Visibility.PUBLIC,
        ).values_list("edition_id", flat=True)
    )
    will_be_published = {
        edition.id for edition in editions if edition.status == Edition.Status.PUBLISHED
    }
    ordered = sorted(
        (
            edition
            for edition in editions
            if edition.status in (Edition.Status.READY, Edition.Status.PUBLISHED)
            and edition.id not in in_flight
        ),
        key=lambda edition: (len(promotion_chain(edition)), edition.slug),
    )
    selected: list[Edition] = []
    for edition in ordered:
        if edition.status == Edition.Status.PUBLISHED:
            if publication_stale(edition) and not publication_blocker(edition):
                selected.append(edition)
            continue
        if edition.source_edition_id and edition.source_edition_id not in will_be_published:
            continue
        if not publication_blocker(edition, allow_unpublished_source=True):
            selected.append(edition)
            will_be_published.add(edition.id)
    return selected


def queue_bulk_publications(editions: list[Edition]) -> list[Edition]:
    """Queue publication of ``editions``, chained per source root so sources land before
    their derived editions while an error in one book never blocks the rest.
    """

    from celery import chain

    from almonium_book_processor.catalog.promotion import promotion_chain
    from almonium_book_processor.catalog.tasks import publish_edition

    by_root: dict[Any, list[Edition]] = {}
    for edition in editions:
        root_id = promotion_chain(edition)[0].id
        by_root.setdefault(root_id, []).append(edition)
    for group in by_root.values():
        if len(group) == 1:
            publish_edition.delay(str(group[0].id))
        else:
            chain(*[publish_edition.si(str(ed.id)) for ed in group]).apply_async()
    return editions
