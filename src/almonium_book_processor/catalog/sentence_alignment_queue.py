"""Which offline sentence alignments the pipeline queues by itself.

Every translation or adaptation is aligned with the original it was made from, as soon
as its text and sentence boundaries are final; an original whose sentences change
queues every edition made from it. The work is local or inside the Modal free credits,
keyed by the pair's text, so queuing the same pair again finds the same run. A pair
already current, queued or running is left alone, in whichever direction it was run.

Only public works are queued: a user's private upload is never aligned unasked.
"""

from __future__ import annotations

import logging

from django.conf import settings

from almonium_book_processor.catalog.models import Edition, Work
from almonium_book_processor.catalog.parallel_content import canonical_root

logger = logging.getLogger(__name__)


def made_from(original: Edition) -> list[Edition]:
    """The editions whose canonical original is ``original``, in a stable order."""

    family = Edition.objects.filter(
        work_id=original.work_id, source_edition__isnull=False, withdrawal_requested_at=None
    ).order_by("language", "cefr_level", "slug")
    return [edition for edition in family if canonical_root(edition) == original.id]


def pairs_for(edition: Edition) -> list[tuple[Edition, Edition]]:
    """(original, other) pairs a change to ``edition`` calls for."""

    if edition.work.visibility != Work.Visibility.PUBLIC or edition.withdrawal_requested_at:
        return []
    root_id = canonical_root(edition)
    if root_id == edition.id:
        return [(edition, other) for other in made_from(edition)]
    original = Edition.objects.get(pk=root_id)
    return [] if original.withdrawal_requested_at else [(original, edition)]


def queue_pair(original: Edition, other: Edition):
    """Queue one pair unless it is current or already under way; the run, or None."""

    from almonium_book_processor.catalog.offline_sentence_alignment import queue_alignment
    from almonium_book_processor.catalog.parallel_status import pair_status

    status = pair_status(original, other)
    if not status["complete"] or status["state"] in {"current", "running"}:
        return None
    try:
        return queue_alignment(original.id, other.id, model=settings.SENTENCE_ALIGNMENT_MODEL)
    except ValueError as error:
        logger.warning(
            "Sentence alignment of %s with %s not queued: %s", original.slug, other.slug, error
        )
        return None


def queue_for(edition: Edition) -> list:
    """Queue every alignment a change to ``edition`` calls for; the runs queued."""

    return [run for pair in pairs_for(edition) if (run := queue_pair(*pair))]
