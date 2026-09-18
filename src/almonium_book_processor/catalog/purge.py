"""Removing a book from Almonium: what has to go, and what has to stay.

A copyright claim, an owner's request, or a mistaken upload all end the same
way: the text must stop being readable anywhere. That is more than a row
delete. The normalized blocks, the uploaded source file, and the book text
sitting inside stored AI request and response payloads all have to go.

Two things survive on purpose. The token ledger keeps its rows, because the
money was really spent and a spend report that quietly shrinks is a broken
report. And an :class:`EditionTombstone` records which book this was, so those
rows still point at something an auditor can read.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from django.db import transaction
from django.utils import timezone

from almonium_book_processor.catalog.models import (
    AIRun,
    Edition,
    EditionTombstone,
)

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractBaseUser

logger = logging.getLogger(__name__)


def blocking_derived_editions(edition: Edition) -> list[Edition]:
    """Editions generated from this one, which would lose their source text."""

    return list(edition.derived_editions.all())


@transaction.atomic
def purge_edition(
    edition: Edition,
    *,
    reason: str,
    notes: str = "",
    actor: AbstractBaseUser | None = None,
    withdrawn: bool = False,
) -> EditionTombstone:
    """Destroy an edition's content and leave an auditable tombstone.

    A published edition must be withdrawn from the product API first: deleting
    the text under a live book would leave readers with a catalogue entry whose
    content endpoint fails. ``withdrawn`` is the withdrawal task's statement
    that the API has already released it.
    """

    if edition.status == Edition.Status.PUBLISHED and not withdrawn:
        raise ValueError("Withdraw this edition from Almonium before purging it.")
    derived = blocking_derived_editions(edition)
    if derived:
        titles = ", ".join(f"{item.title} ({item.language.upper()})" for item in derived)
        raise ValueError(f"Purge the editions generated from this one first: {titles}")

    work = edition.work
    tombstone = EditionTombstone.objects.create(
        edition_id=edition.id,
        edition_slug=edition.slug,
        work_slug=work.slug,
        title=edition.title,
        author=edition.author,
        language=edition.language,
        edition_type=edition.edition_type,
        source_sha256=edition.source_sha256,
        word_count=edition.word_count,
        was_published=edition.published_book_id is not None,
        published_book_id=edition.published_book_id,
        reason=reason,
        notes=notes,
        purged_by=actor if actor is not None and actor.is_authenticated else None,
    )
    # The payloads carry the book's own words. Keep the counts and the cost.
    AIRun.objects.filter(edition=edition).update(
        edition=None,
        pipeline_run=None,
        tombstone=tombstone,
        request_payload={},
        response_payload={},
        updated_at=timezone.now(),
    )

    source_name = edition.source_file.name
    storage = edition.source_file.storage
    edition.delete()
    if not work.editions.exists():
        work.delete()
    else:
        from almonium_book_processor.catalog.adaptation_floor import refresh_adaptation_floor

        refresh_adaptation_floor(work)
    if source_name:
        # Only once the deletion is committed: a rolled back transaction must
        # not leave an edition pointing at a file that is already gone.
        transaction.on_commit(lambda: _delete_source_file(storage, source_name))
    return tombstone


def _delete_source_file(storage, name: str) -> None:
    try:
        storage.delete(name)
    except Exception:
        logger.exception("Purged edition left its source file behind: %s", name)


def removal_blocker(edition: Edition) -> str:
    """Why this edition cannot be removed at all right now, or an empty string.

    Being published is not a blocker: it only decides whether the removal has to
    tell the product API first.
    """

    derived = blocking_derived_editions(edition)
    if not derived:
        return ""
    titles = ", ".join(f"{item.title} ({item.language.upper()})" for item in derived)
    return f"Editions generated from this one must go first: {titles}"
