"""Drop inferred alignment from editions that are aligned by construction.

A canonical or generated parallel edition inherits its block groups from the
canonical original, so its correspondence is exact. Inferred rows written over
that identity replace certainty with a confidence score, and they raise a
review queue the edition is not supposed to have.
"""

from __future__ import annotations

import contextlib
import uuid

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Q

from almonium_book_processor.catalog.models import (
    AlignmentGroupReview,
    BlockAlignment,
    ChapterAlignment,
    Edition,
    PipelineRun,
    QAWarning,
)

ALIGNMENT_WARNING_CODES = (
    "alignment_low_confidence",
    "alignment_chapter_low_confidence",
    "alignment_incomplete",
)


class Command(BaseCommand):
    help = "Delete inferred alignment rows from editions that are aligned by construction."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--edition",
            dest="edition",
            default="",
            help="Restrict to one edition, by id or slug. Defaults to every affected edition.",
        )
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Delete the rows. Without this the command only reports what it would delete.",
        )

    def handle(self, *args, **options) -> None:
        editions = self._select_editions(options["edition"])
        affected = [edition for edition in editions if not edition.requires_inferred_alignment]
        if not affected:
            self.stdout.write("No edition holds inferred alignment it should not have.")
            return

        total = 0
        for edition in affected:
            counts = self._counts(edition)
            if not any(counts.values()):
                continue
            total += sum(counts.values())
            self.stdout.write(
                self.style.WARNING(f"{edition} ({edition.get_parallel_role_display()})")
            )
            for label, count in counts.items():
                self.stdout.write(f"  {label}: {count}")
            if options["apply"]:
                with transaction.atomic():
                    self._queryset(edition, AlignmentGroupReview).delete()
                    self._queryset(edition, BlockAlignment).delete()
                    self._queryset(edition, ChapterAlignment).delete()
                    self._warnings(edition).delete()
                    self._runs(edition).delete()

        if not total:
            self.stdout.write("No edition holds inferred alignment it should not have.")
        elif options["apply"]:
            self.stdout.write(self.style.SUCCESS(f"Deleted {total} inferred alignment rows."))
        else:
            self.stdout.write(f"Would delete {total} rows. Re-run with --apply to do it.")

    def _select_editions(self, identifier: str):
        editions = Edition.objects.select_related("source_edition").order_by("slug")
        if not identifier:
            return editions
        lookup = Q(slug=identifier)
        with contextlib.suppress(ValueError):
            lookup |= Q(id=uuid.UUID(identifier))
        edition = editions.filter(lookup).first()
        if edition is None:
            raise CommandError(f"No edition matches {identifier!r}.")
        return [edition]

    def _counts(self, edition: Edition) -> dict[str, int]:
        return {
            "block alignments": self._queryset(edition, BlockAlignment).count(),
            "chapter alignments": self._queryset(edition, ChapterAlignment).count(),
            "group reviews": self._queryset(edition, AlignmentGroupReview).count(),
            "alignment warnings": self._warnings(edition).count(),
            "align pipeline runs": self._runs(edition).count(),
        }

    def _queryset(self, edition: Edition, model):
        return model.objects.filter(target_edition=edition)

    def _warnings(self, edition: Edition):
        return QAWarning.objects.filter(edition=edition, code__in=ALIGNMENT_WARNING_CODES)

    def _runs(self, edition: Edition):
        return PipelineRun.objects.filter(edition=edition, stage=PipelineRun.Stage.ALIGN)
