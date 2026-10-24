"""Rebuild a source ingest's chapters from the file it already downloaded.

When the importer learns to read a book better (a Gutenberg file that holds
twenty chapters in one document, say), the editions already on the shelf keep
the old reading until they are made again. Pre-launch, nothing made from them
is worth keeping: the editions generated from the source go, every finished
pipeline run goes (each stage keys its run on the source hash and would hand
back the old result as it stands), and the same pipeline a download starts
runs again on the stored file.
"""

from __future__ import annotations

from django.db import transaction

from almonium_book_processor.catalog.models import Edition, RemovalReason, SourceDownload
from almonium_book_processor.catalog.purge import purge_edition


class CannotReingest(ValueError):
    """The edition is not a downloaded source ingest that may be rebuilt now."""


@transaction.atomic
def reset_for_reingest(edition: Edition) -> list[str]:
    """Clear what was built from the edition's file; returns the derived editions purged.

    The caller queues ``tasks.process_book_pipeline`` once this commits. A
    published edition, or one being withdrawn, is refused: the product API
    serves its chapters, and rebuilding them under it is the purge module's
    invariant to keep, not this one's to break.
    """

    record = getattr(edition, "source_download", None)
    if record is None:
        raise CannotReingest(f"{edition.slug} was not created by a source ingest.")
    if record.status != SourceDownload.Status.DOWNLOADED or not edition.source_file:
        raise CannotReingest(f"{edition.slug} has no downloaded file to read again.")
    if edition.status == Edition.Status.PUBLISHED or edition.withdrawal_requested_at:
        raise CannotReingest(f"{edition.slug} is published; withdraw it before rebuilding it.")

    purged = _purge_derived(edition)
    edition.pipeline_runs.all().delete()
    edition.artifacts.all().delete()
    edition.text_quality_findings.all().delete()
    edition.review_decisions.all().delete()
    edition.chapters.all().delete()
    edition.warnings.all().delete()
    edition.status = Edition.Status.QUEUED
    edition.word_count = 0
    edition.save(update_fields=["status", "word_count", "updated_at"])
    # The factory reports the book finished once; a rebuilt book is reported again.
    record.reported_final = False
    record.save(update_fields=["reported_final", "updated_at"])
    return purged


def _purge_derived(edition: Edition) -> list[str]:
    purged: list[str] = []
    for derived in list(edition.derived_editions.all()):
        purged.extend(_purge_derived(derived))
        if derived.status == Edition.Status.PUBLISHED or derived.withdrawal_requested_at:
            raise CannotReingest(
                f"{derived.slug}, made from {edition.slug}, is published; withdraw it first."
            )
        purge_edition(
            derived,
            reason=RemovalReason.MISTAKE,
            notes=f"Removed by reingest_source to rebuild {edition.slug} from its file.",
            force=True,
        )
        purged.append(derived.slug)
    return purged
