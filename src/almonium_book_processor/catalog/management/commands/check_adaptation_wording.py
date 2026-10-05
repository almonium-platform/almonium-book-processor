import time

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from almonium_book_processor.catalog.adaptation_quality import (
    adaptation_target,
    sync_difficulty_warning,
)
from almonium_book_processor.catalog.adaptation_wording import (
    carry_wording_forward,
    check_chapter,
    check_edition,
    revise_chapter,
    spot_fix_chapter,
)
from almonium_book_processor.catalog.chapter_analysis import analysis_context
from almonium_book_processor.catalog.chapter_projections import LEVELS
from almonium_book_processor.catalog.models import Edition, PipelineRun


class Command(BaseCommand):
    help = (
        "Have the pilot's level judges read every chapter of an adapted edition for its "
        "wording, so the edition's level gate uses their reading. With --revise, a "
        "substantive chapter read above the target is mended: the adapter rewrites the "
        "paragraphs the judges cited, and if they still read the chapter above the target it "
        "goes back to the adapter whole, once, where its length allows. Run on the machine "
        "where the judges' CLIs are signed in."
    )

    def add_arguments(self, parser):
        parser.add_argument("edition_slug")
        parser.add_argument("--workers", type=int, default=3, help="chapters read at a time")
        parser.add_argument("--revise", action="store_true")
        parser.add_argument(
            "--idle-timeout",
            type=int,
            default=1800,
            help="seconds to wait for the edition's other jobs before applying a revision",
        )

    def handle(self, *args, **options):
        try:
            edition = Edition.objects.select_related("source_edition").get(
                slug=options["edition_slug"]
            )
        except Edition.DoesNotExist as error:
            raise CommandError(f"No edition with slug {options['edition_slug']}") from error
        target = adaptation_target(edition)
        if target not in LEVELS:
            raise CommandError("The edition has no single adaptation target.")
        for kept in carry_wording_forward(edition):
            self.stdout.write(
                f"{kept['sequence']:>3} changed by {100 * kept['change']:.2f}% of its words: "
                "the judges' reading is kept"
            )
        verdicts = check_edition(edition, workers=options["workers"])
        for chapter in edition.chapters.order_by("sequence"):
            verdict = verdicts.get(str(chapter.id))
            if verdict is None:
                continue
            above = LEVELS.index(verdict["max_level"]) > LEVELS.index(target)
            line = f"{chapter.sequence:>3} {chapter.title[:28]:28} {verdict['max_level']}"
            line += "  " + "; ".join(
                f"{judge['model']} {', '.join(judge['readings'])}"
                for judge in verdict.get("judges", [])
            )
            if above and options["revise"] and chapter.analysis_role == "body":
                line += self._mend(edition, chapter, verdict, target, options["idle_timeout"])
            elif above:
                line += "  (above the target)"
            self.stdout.write(line)
        self._sync_review_item(edition)

    def _sync_review_item(self, edition) -> None:
        """The edition's difficulty review item follows what the judges just read."""

        run = analysis_context(edition).get("chapter_analysis_run")
        if run is None:
            return
        with transaction.atomic():
            sync_difficulty_warning(Edition.objects.select_for_update().get(pk=edition.id), run)

    def _mend(self, edition, chapter, verdict, target, timeout: int) -> str:
        """The cited paragraphs first; the whole chapter once if that was not enough."""

        def too_hard(reading) -> bool:
            return LEVELS.index(reading["max_level"]) > LEVELS.index(target)

        self._wait_idle(edition, timeout)
        spot = spot_fix_chapter(edition, edition.chapters.get(pk=chapter.id))
        note = f"  -> {spot['changed']} cited paragraph(s) rewritten"
        if spot["skipped"]:
            note += f" ({len(spot['skipped'])} left: {'; '.join(spot['skipped'])})"
        if spot["changed"]:
            self._wait_idle(edition, timeout)
            verdict = check_chapter(edition, edition.chapters.get(pk=chapter.id))
            note += f", now read {verdict['max_level']}"
            if not too_hard(verdict):
                return note
        self._wait_idle(edition, timeout)
        outcome = revise_chapter(edition, edition.chapters.get(pk=chapter.id), verdict)
        if not outcome["applied"]:
            return note + f"; whole chapter not revised: {outcome['reason']}"
        self._wait_idle(edition, timeout)
        reread = check_chapter(edition, edition.chapters.get(pk=chapter.id))
        return note + f"; whole chapter revised and applied, now read {reread['max_level']}"

    def _wait_idle(self, edition, timeout: int) -> None:
        """A revision replaces a chapter, which the edition refuses while its jobs run."""

        deadline = time.monotonic() + timeout
        while edition.pipeline_runs.filter(
            status__in=[PipelineRun.Status.QUEUED, PipelineRun.Status.RUNNING]
        ).exists():
            if time.monotonic() > deadline:
                raise CommandError("The edition's other jobs did not finish in time.")
            time.sleep(10)
