"""Carrying a finished edition to another environment without reprocessing it.

Every environment runs its own processor, and its product API reads book text
from that processor alone. So a book that was ingested, aligned, analysed and
reviewed locally does not exist on staging until its data is carried there.
Running the pipeline again would pay every model call a second time; a bundle
carries the results instead.

A bundle is a zip holding ``manifest.json`` and the uploaded source files. The
manifest lists the edition, every edition it was generated from, and each
edition's rows: chapters, blocks, revisions, pipeline runs, artifacts, quality
findings, warnings, review decisions and alignments. Primary keys travel with
the rows, because artifact payloads and alignment groups refer to blocks and
chapters by id, so the same edition has the same ids in every environment.

Only current artifacts travel. Every text revision retires the edition's
artifacts and the refresh regenerates them, so an edited edition accumulates
retired lexical profiles and sentence alignments that nothing reads but that
would dominate the bundle. A retired artifact still travels while a quality
finding points at it, because the finding's row names it.

Two things stay behind on purpose. The AI run ledger records what this
environment paid, and each product API sums its own processor's ledger, so a
copied ledger would count the same money twice. And publication state belongs
to the environment: the target decides when its own product API learns about
the book.
"""

from __future__ import annotations

import hashlib
import io
import json
import logging
import os
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.serializers.json import DjangoJSONEncoder
from django.db import connection, transaction
from django.db.migrations.recorder import MigrationRecorder
from django.db.models import Q
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from almonium_book_processor import __version__
from almonium_book_processor.catalog.models import (
    AlignmentGroupReview,
    BlockAlignment,
    Chapter,
    ChapterAlignment,
    ContentBlock,
    ContentBlockRevision,
    Edition,
    EditionArtifact,
    PipelineRun,
    QAWarning,
    ReviewDecision,
    TextQualityFinding,
    Work,
)

logger = logging.getLogger(__name__)

# Bump when the manifest's shape changes. A target running an older build
# refuses a newer bundle instead of silently dropping what it does not know.
BUNDLE_SCHEMA_VERSION = 5
MANIFEST_NAME = "manifest.json"

# Runs that describe what an environment did with its own product API, or
# with other environments, and so never describe the edition itself.
LOCAL_RUN_STAGES = (PipelineRun.Stage.PUBLISH, PipelineRun.Stage.PROMOTE)


class PromotionError(RuntimeError):
    pass


@dataclass(frozen=True)
class PromotionTarget:
    """Another deployment of this service that finished editions are copied to.

    Targets are deployment configuration, like the product API's publisher
    secret: ``ALMONIUM_BOOKS_PROMOTION_TARGETS`` names them as
    ``name=https://host`` pairs and ``ALMONIUM_BOOKS_PROMOTION_TOKEN_<NAME>``
    holds the token that target accepts. Which environments may write to which
    is therefore decided in the infrastructure vaults, never on a page.
    """

    name: str
    base_url: str
    token: str


def promotion_targets() -> list[PromotionTarget]:
    """The targets this environment is configured to push to, tokens present."""

    targets = []
    for entry in os.getenv("ALMONIUM_BOOKS_PROMOTION_TARGETS", "").split(","):
        name, _, base_url = entry.strip().partition("=")
        name, base_url = name.strip(), base_url.strip().rstrip("/")
        if not name or not base_url:
            continue
        token = os.getenv(f"ALMONIUM_BOOKS_PROMOTION_TOKEN_{name.upper()}", "")
        if token:
            targets.append(PromotionTarget(name=name, base_url=base_url, token=token))
    return targets


def promotion_target(name: str | None) -> PromotionTarget | None:
    return next((target for target in promotion_targets() if target.name == name), None)


def accepted_promotion_token() -> str:
    """The token this environment requires from a source that pushes here."""

    return os.getenv("ALMONIUM_BOOKS_PROMOTION_TOKEN", "")


# --------------------------------------------------------------------------
# Row shapes. Every list is the exact set of columns that travels; a column
# added to a model does not travel until it is named here, which is what the
# bundle schema version protects.

WORK_FIELDS = [
    "id",
    "slug",
    "title",
    "author",
    "description",
    "original_language",
    "publication_year",
    "cover_url",
    "visibility",
    "metadata_provenance",
    "metadata_detected_at",
    "metadata_confirmed_at",
    # The floor and its evidence are found where the judge and audit ran;
    # the receiving environment keeps them rather than recomputing from a
    # ledger it does not have.
    "adapts_to",
    "adaptation_evidence",
    "created_at",
    "updated_at",
]
EDITION_FIELDS = [
    "id",
    "slug",
    "work_id",
    "source_edition_id",
    "title",
    "author",
    "description",
    "language",
    "edition_type",
    "translator",
    "literary_register",
    "cefr_level",
    "cefr_level_source",
    "parallel_role",
    "schema_version",
    "status",
    "word_count",
    "source_sha256",
    "created_at",
    "updated_at",
]
CHAPTER_FIELDS = [
    "id",
    "edition_id",
    "sequence",
    "title",
    "analysis_role",
    "created_at",
    "updated_at",
]
BLOCK_FIELDS = [
    "id",
    "edition_id",
    "chapter_id",
    "block_id",
    "sequence",
    "block_type",
    "text",
    "sentences",
    "align_group",
    "source_ref",
    "attributes",
    "created_at",
    "updated_at",
]
REVISION_FIELDS = [
    "id",
    "edition_id",
    "block_id",
    "stable_block_id",
    "previous_text",
    "revised_text",
    "notes",
    "created_at",
    "updated_at",
]
RUN_FIELDS = [
    "id",
    "edition_id",
    "stage",
    "status",
    "idempotency_key",
    "processor_version",
    "input_hash",
    "progress",
    "confidence",
    "started_at",
    "finished_at",
    "summary",
    "error",
    "created_at",
    "updated_at",
]
ARTIFACT_FIELDS = [
    "id",
    "edition_id",
    "chapter_id",
    "pipeline_run_id",
    "kind",
    "schema_version",
    "input_hash",
    "processor_version",
    "payload",
    "is_current",
    "created_at",
    "updated_at",
]
FINDING_FIELDS = [
    "id",
    "edition_id",
    "pipeline_run_id",
    "artifact_id",
    "block_id",
    "stable_block_id",
    "input_hash",
    "fingerprint",
    "code",
    "status",
    "start_offset",
    "end_offset",
    "original_text",
    "suggested_text",
    "confidence",
    "message",
    "evidence",
    "reviewed_at",
    "created_at",
    "updated_at",
]
WARNING_FIELDS = [
    "id",
    "edition_id",
    "pipeline_run_id",
    "block_id",
    "code",
    "severity",
    "message",
    "source_ref",
    "resolved_at",
    "created_at",
    "updated_at",
]
DECISION_FIELDS = [
    "id",
    "edition_id",
    "decision",
    "notes",
    "source_sha256",
    "actionable_warning_count",
    "created_at",
    "updated_at",
]
GROUP_REVIEW_FIELDS = [
    "id",
    "target_edition_id",
    "group_id",
    "decision",
    "source_block_ids",
    "target_block_ids",
    "notes",
    "created_at",
    "updated_at",
]
BLOCK_ALIGNMENT_FIELDS = [
    "id",
    "source_edition_id",
    "target_edition_id",
    "source_block_id",
    "target_block_id",
    "group_id",
    "confidence",
    "strategy",
    "created_at",
    "updated_at",
]
CHAPTER_ALIGNMENT_FIELDS = [
    "id",
    "source_edition_id",
    "target_edition_id",
    "source_chapter_id",
    "target_chapter_id",
    "group_id",
    "confidence",
    "strategy",
    "created_at",
    "updated_at",
]

# Each table an edition owns: the manifest key, the model, the columns that
# travel, the user column that becomes a username, the field that scopes the
# rows to their edition, and the order rows are written in.
EDITION_TABLES = [
    ("chapters", Chapter, CHAPTER_FIELDS, None, "edition_id"),
    ("blocks", ContentBlock, BLOCK_FIELDS, None, "edition_id"),
    ("pipeline_runs", PipelineRun, RUN_FIELDS, None, "edition_id"),
    ("artifacts", EditionArtifact, ARTIFACT_FIELDS, None, "edition_id"),
    ("block_revisions", ContentBlockRevision, REVISION_FIELDS, "editor", "edition_id"),
    ("text_quality_findings", TextQualityFinding, FINDING_FIELDS, "reviewed_by", "edition_id"),
    ("warnings", QAWarning, WARNING_FIELDS, "resolved_by", "edition_id"),
    ("review_decisions", ReviewDecision, DECISION_FIELDS, "reviewer", "edition_id"),
    (
        "alignment_group_reviews",
        AlignmentGroupReview,
        GROUP_REVIEW_FIELDS,
        "reviewer",
        "target_edition_id",
    ),
    ("chapter_alignments", ChapterAlignment, CHAPTER_ALIGNMENT_FIELDS, None, "target_edition_id"),
    ("block_alignments", BlockAlignment, BLOCK_ALIGNMENT_FIELDS, None, "target_edition_id"),
]
DATETIME_COLUMNS = {
    "created_at",
    "updated_at",
    "started_at",
    "finished_at",
    "resolved_at",
    "reviewed_at",
    "metadata_detected_at",
    "metadata_confirmed_at",
}


# --------------------------------------------------------------------------
# What this environment is.


def origin_label() -> str:
    """The name other environments know this one by: its public host, or local."""

    for host in settings.ALLOWED_HOSTS:
        if host not in {"localhost", "127.0.0.1", "0.0.0.0", "testserver", "*"}:
            return host
    return "local"


def catalog_migration() -> str:
    """The newest catalog migration applied here, which fixes the row shapes."""

    applied = MigrationRecorder(connection).applied_migrations()
    names = [name for app, name in applied if app == "catalog"]
    return max(names) if names else ""


def capabilities(slugs: list[str] | None = None) -> dict[str, Any]:
    """What a source has to know before pushing here, plus what we hold."""

    editions = Edition.objects.filter(slug__in=slugs or []).only(
        "slug", "id", "status", "source_sha256", "promotion_fingerprint"
    )
    return {
        "processor_version": __version__,
        "bundle_schema_version": BUNDLE_SCHEMA_VERSION,
        "catalog_migration": catalog_migration(),
        "origin": origin_label(),
        "editions": {
            edition.slug: {
                "id": str(edition.id),
                "status": edition.status,
                "source_sha256": edition.source_sha256,
                "promotion_fingerprint": edition.promotion_fingerprint,
            }
            for edition in editions
        },
    }


def compatibility_problem(target: dict[str, Any]) -> str:
    """Why a bundle made here cannot be imported by that target, or empty."""

    schema = target.get("bundle_schema_version")
    if schema != BUNDLE_SCHEMA_VERSION:
        return (
            f"The target understands bundle schema {schema}, this build writes "
            f"{BUNDLE_SCHEMA_VERSION}; deploy the same build to both sides first."
        )
    migration = target.get("catalog_migration")
    ours = catalog_migration()
    if migration != ours:
        return (
            f"The target's catalog schema is at {migration or 'an unknown migration'}, "
            f"this one is at {ours}; deploy the same build to both sides first."
        )
    return ""


def source_compatibility_problem(source: dict[str, Any]) -> str:
    """Why a bundle written by that environment cannot land here, or empty."""

    schema = source.get("bundle_schema_version")
    if schema != BUNDLE_SCHEMA_VERSION:
        return (
            f"{source.get('origin') or 'The source'} writes bundle schema {schema}, this "
            f"build reads {BUNDLE_SCHEMA_VERSION}; deploy the same build to both sides first."
        )
    migration = source.get("catalog_migration")
    ours = catalog_migration()
    if migration != ours:
        return (
            f"{source.get('origin') or 'The source'} is at catalog migration "
            f"{migration or 'unknown'}, this environment is at {ours}; deploy the same "
            "build to both sides first."
        )
    return ""


# --------------------------------------------------------------------------
# Export.


def promotion_chain(edition: Edition) -> list[Edition]:
    """The edition and everything it was generated from, sources first."""

    chain: list[Edition] = []
    current: Edition | None = edition
    while current is not None:
        chain.append(current)
        current = current.source_edition
    chain.reverse()
    return chain


def promotion_blocker(edition: Edition) -> str:
    """Why this edition cannot leave this environment yet, or an empty string."""

    if edition.work.visibility != Work.Visibility.PUBLIC:
        return "Private imports belong to their owner and are never promoted."
    for item in promotion_chain(edition):
        if item.status not in {Edition.Status.READY, Edition.Status.PUBLISHED}:
            what = "This edition" if item.id == edition.id else f"Its source {item.slug}"
            return (
                f"{what} has not passed review yet ({item.get_status_display().lower()}); "
                "only reviewed editions travel."
            )
    return ""


def exportable_editions() -> list[Edition]:
    """Every edition that may leave this environment, in slug order."""

    candidates = (
        Edition.objects.filter(
            status__in=[Edition.Status.READY, Edition.Status.PUBLISHED],
            work__visibility=Work.Visibility.PUBLIC,
        )
        .select_related("work", "source_edition")
        .order_by("slug")
    )
    return [edition for edition in candidates if not promotion_blocker(edition)]


def export_listing() -> dict[str, Any]:
    """What a puller has to know: what this build writes, and what may leave.

    Each entry names its source edition, so a puller that wants everything
    can fetch only the editions nothing else was generated from; their
    bundles carry the sources.
    """

    return {
        "processor_version": __version__,
        "bundle_schema_version": BUNDLE_SCHEMA_VERSION,
        "catalog_migration": catalog_migration(),
        "origin": origin_label(),
        "editions": [
            {
                "slug": edition.slug,
                "id": str(edition.id),
                "status": edition.status,
                "source_edition": edition.source_edition.slug if edition.source_edition else None,
            }
            for edition in exportable_editions()
        ],
    }


def _row(instance, fields: list[str], user_field: str | None) -> dict[str, Any]:
    row = {name: getattr(instance, name) for name in fields}
    if user_field:
        user = getattr(instance, user_field)
        row[f"{user_field}_username"] = user.get_username() if user else None
    return row


def _edition_section(edition: Edition) -> dict[str, Any]:
    section: dict[str, Any] = {"edition": _row(edition, EDITION_FIELDS, None)}
    # A generated or legacy-imported edition has no upload; its text is its blocks.
    section["edition"]["source_file"] = (
        Path(edition.source_file.name).name if edition.source_file else None
    )
    for key, model, fields, user_field, scope in EDITION_TABLES:
        queryset = model.objects.filter(**{scope: edition.id}).order_by("id")
        if model is PipelineRun:
            queryset = queryset.exclude(stage__in=LOCAL_RUN_STAGES)
        if model is EditionArtifact:
            queryset = queryset.filter(
                Q(is_current=True) | Q(text_quality_findings__edition_id=edition.id)
            ).distinct()
        if user_field:
            queryset = queryset.select_related(user_field)
        section[key] = [_row(item, fields, user_field) for item in queryset]
    return section


class _Encoder(DjangoJSONEncoder):
    """Django's encoder, but with the microseconds a row's ordering depends on."""

    def default(self, o):
        if isinstance(o, datetime):
            return o.isoformat()
        return super().default(o)


def _canonical(payload: Any) -> bytes:
    return json.dumps(payload, cls=_Encoder, sort_keys=True, separators=(",", ":")).encode()


def _fingerprint(section: dict[str, Any]) -> str:
    return hashlib.sha256(_canonical(section)).hexdigest()


def build_manifest(edition: Edition) -> dict[str, Any]:
    chain = promotion_chain(edition)
    works: dict[Any, Work] = {}
    editions = []
    for item in chain:
        works[item.work_id] = item.work
        section = _edition_section(item)
        section["fingerprint"] = _fingerprint(section)
        editions.append(section)
    return {
        "bundle_schema_version": BUNDLE_SCHEMA_VERSION,
        "processor_version": __version__,
        "catalog_migration": catalog_migration(),
        "origin": origin_label(),
        "exported_at": timezone.now(),
        "edition_slug": edition.slug,
        # The content's own digest: the same editions bundled again tomorrow
        # hash the same, whatever the export time or origin says.
        "bundle_hash": hashlib.sha256(
            _canonical([section["fingerprint"] for section in editions])
        ).hexdigest(),
        "works": [_row(work, WORK_FIELDS, None) for work in works.values()],
        "editions": editions,
    }


def export_bundle(edition: Edition) -> bytes:
    """Serialize the edition and its sources into a zip an import can replay."""

    blocked = promotion_blocker(edition)
    if blocked:
        raise PromotionError(blocked)
    manifest = build_manifest(edition)
    by_id = {str(item.id): item for item in promotion_chain(edition)}
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(MANIFEST_NAME, _canonical(manifest))
        for section in manifest["editions"]:
            row = section["edition"]
            if not row["source_file"]:
                continue
            with by_id[str(row["id"])].source_file.open("rb") as handle:
                archive.writestr(f"sources/{row['id']}/{row['source_file']}", handle.read())
    return buffer.getvalue()


def bundle_hash(data: bytes) -> str:
    """The content's digest: the same editions bundled twice hash the same."""

    manifest, _archive = _read_manifest(data)
    return manifest["bundle_hash"]


# --------------------------------------------------------------------------
# Import.


def _parse(row: dict[str, Any]) -> dict[str, Any]:
    parsed = dict(row)
    for name in DATETIME_COLUMNS & parsed.keys():
        value = parsed[name]
        if isinstance(value, str):
            parsed[name] = parse_datetime(value)
    return parsed


def _read_manifest(data: bytes) -> tuple[dict[str, Any], zipfile.ZipFile]:
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
        manifest = json.loads(archive.read(MANIFEST_NAME))
    except (zipfile.BadZipFile, KeyError, json.JSONDecodeError) as error:
        raise PromotionError("This is not an edition bundle.") from error
    schema = manifest.get("bundle_schema_version")
    if schema != BUNDLE_SCHEMA_VERSION:
        raise PromotionError(
            f"Bundle schema {schema} is not the {BUNDLE_SCHEMA_VERSION} this build reads."
        )
    if manifest.get("catalog_migration") != catalog_migration():
        raise PromotionError(
            f"The bundle was written at catalog migration {manifest.get('catalog_migration')}, "
            f"this environment is at {catalog_migration()}."
        )
    return manifest, archive


def _usernames(manifest: dict[str, Any]) -> dict[str, Any]:
    wanted: set[str] = set()
    for section in manifest["editions"]:
        for key, _model, _fields, user_field, _scope in EDITION_TABLES:
            if user_field:
                wanted.update(
                    row[f"{user_field}_username"]
                    for row in section[key]
                    if row.get(f"{user_field}_username")
                )
    if not wanted:
        return {}
    users = get_user_model().objects.filter(username__in=wanted)
    return {user.get_username(): user for user in users}


def _upsert(model, rows: list[dict[str, Any]], fields: list[str]) -> None:
    """Insert or replace rows by primary key, keeping the timestamps they carry.

    An insert applies the models' automatic timestamps, which would date every
    promoted row at the import instead of when the work really happened, so
    the carried values are written back afterwards.
    """

    if not rows:
        return
    objects = [model(**row) for row in rows]
    stamps = {row["id"]: (row["created_at"], row["updated_at"]) for row in rows}
    model.objects.bulk_create(
        objects,
        update_conflicts=True,
        unique_fields=["id"],
        update_fields=[name for name in fields if name != "id"],
        batch_size=500,
    )
    for obj in objects:
        obj.created_at, obj.updated_at = stamps[obj.id]
    model.objects.bulk_update(objects, ["created_at", "updated_at"], batch_size=500)


def _slug_conflict(model, slug: str, row_id: str) -> None:
    if model.objects.filter(slug=slug).exclude(id=row_id).exists():
        raise PromotionError(
            f"A different {model.__name__.lower()} already uses the slug {slug} here; "
            "remove it before promoting this one."
        )


def _import_work(row: dict[str, Any]) -> None:
    if row["visibility"] != Work.Visibility.PUBLIC:
        raise PromotionError(f"Work {row['slug']} is a private import and cannot be promoted.")
    _slug_conflict(Work, row["slug"], row["id"])
    _upsert(Work, [_parse(row)], WORK_FIELDS)


def _import_edition(
    section: dict[str, Any],
    archive: zipfile.ZipFile,
    users: dict[str, Any],
    origin: str,
) -> Edition:
    row = _parse(section["edition"])
    source_name = row.pop("source_file")
    _slug_conflict(Edition, row["slug"], row["id"])
    existing = Edition.objects.filter(id=row["id"]).first()
    values = {name: row[name] for name in EDITION_FIELDS if name != "id"}
    # Publication is this environment's own state: the bundle's status says the
    # edition was reviewed, so it lands ready here unless it is already live.
    values["status"] = (
        Edition.Status.PUBLISHED
        if existing and existing.status == Edition.Status.PUBLISHED
        else Edition.Status.READY
    )
    values.update(
        promoted_from=origin,
        promoted_at=timezone.now(),
        promotion_fingerprint=section["fingerprint"],
    )
    if existing:
        edition = existing
        for name, value in values.items():
            setattr(edition, name, value)
    else:
        edition = Edition(id=row["id"], **values)
    previous_file = existing.source_file.name if existing else ""
    if source_name:
        edition.source_file.save(
            source_name,
            ContentFile(archive.read(f"sources/{row['id']}/{source_name}")),
            save=False,
        )
    else:
        edition.source_file = None
    edition.save()
    # save() refreshed updated_at; keep the carried one so the fingerprint and
    # the page agree on when the edition last changed.
    Edition.objects.filter(id=edition.id).update(
        created_at=row["created_at"], updated_at=row["updated_at"]
    )
    if previous_file and previous_file != edition.source_file.name:
        storage = edition.source_file.storage
        transaction.on_commit(lambda: storage.delete(previous_file))

    for key, model, fields, user_field, scope in EDITION_TABLES:
        rows = []
        for raw in section[key]:
            parsed = _parse(raw)
            if user_field:
                parsed[user_field] = users.get(parsed.pop(f"{user_field}_username", None))
            rows.append(parsed)
        stale = model.objects.filter(**{scope: edition.id}).exclude(
            id__in=[item["id"] for item in rows]
        )
        if model is PipelineRun:
            stale = stale.exclude(stage__in=LOCAL_RUN_STAGES)
        stale.delete()
        _upsert(model, rows, fields + ([user_field] if user_field else []))
    return edition


def import_bundle(data: bytes, *, origin: str | None = None) -> dict[str, Any]:
    """Land a bundle here, replacing what an earlier promotion left.

    Returns which editions were written and which were already current. The
    whole bundle lands in one transaction, so a refused edition leaves nothing
    half-copied behind.
    """

    manifest, archive = _read_manifest(data)
    origin = origin or manifest.get("origin") or "unknown"
    users = _usernames(manifest)
    imported: list[str] = []
    skipped: list[str] = []
    with transaction.atomic():
        for row in manifest["works"]:
            _import_work(row)
        for section in manifest["editions"]:
            slug = section["edition"]["slug"]
            current = (
                Edition.objects.filter(id=section["edition"]["id"])
                .values_list("promotion_fingerprint", flat=True)
                .first()
            )
            if current == section["fingerprint"]:
                skipped.append(slug)
                continue
            _import_edition(section, archive, users, origin)
            imported.append(slug)
    logger.info("Promotion from %s landed: imported %s, skipped %s", origin, imported, skipped)
    return {
        "bundle_hash": manifest["bundle_hash"],
        "edition_slug": manifest["edition_slug"],
        "origin": origin,
        "imported": imported,
        "skipped": skipped,
    }


def bundle_editions(data: bytes) -> list[str]:
    """The slugs a bundle carries, sources first."""

    manifest, _archive = _read_manifest(data)
    return [section["edition"]["slug"] for section in manifest["editions"]]


def queue_publications(slugs: list[str]) -> list[str]:
    """Queue this environment's own publication of promoted editions, sources first.

    The product API is told about each edition in turn, because a derived
    edition cannot be published before the edition it was generated from is.
    Returns the slugs that were queued; an edition already live here is not
    published again.
    """

    from celery import chain

    from almonium_book_processor.catalog.tasks import publish_edition

    editions = {edition.slug: edition for edition in Edition.objects.filter(slug__in=slugs)}
    pending = [
        editions[slug]
        for slug in slugs
        if slug in editions and editions[slug].status != Edition.Status.PUBLISHED
    ]
    if pending:
        chain(*[publish_edition.si(str(edition.id)) for edition in pending]).apply_async()
    return [edition.slug for edition in pending]
