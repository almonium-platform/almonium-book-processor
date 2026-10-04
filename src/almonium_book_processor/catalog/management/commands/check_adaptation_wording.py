import time

from django.core.management.base import BaseCommand, CommandError

from almonium_book_processor.catalog.adaptation_quality import adaptation_target
from almonium_book_processor.catalog.adaptation_wording import (
    check_chapter,
    check_edition,
    revise_chapter,
)
from almonium_book_processor.catalog.chapter_projections import LEVELS
from almonium_book_processor.catalog.models import Edition, PipelineRun


class Command(BaseCommand):
    help = (
        "Have the pilot's level judges read every chapter of an adapted edition for its "
        "wording, so the edition's level gate uses their reading. With --revise, a "
        "substantive chapter read above the target goes back to the adapter once with what "
        "the judges cited, and the revision is applied if they read it at the target. Run on "
        "the machine where the judges' CLIs are signed in."
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
                self._wait_idle(edition, options["idle_timeout"])
                chapter.refresh_from_db()
                outcome = revise_chapter(edition, chapter, verdict)
                if outcome["applied"]:
                    self._wait_idle(edition, options["idle_timeout"])
                    reread = check_chapter(edition, edition.chapters.get(pk=chapter.id))
                    line += f"  -> revised and applied, now read {reread['max_level']}"
                else:
                    line += f"  -> not revised: {outcome['reason']}"
            elif above:
                line += "  (above the target)"
            self.stdout.write(line)

    def _wait_idle(self, edition, timeout: int) -> None:
        """A revision replaces a chapter, which the edition refuses while its jobs run."""

        deadline = time.monotonic() + timeout
        while edition.pipeline_runs.filter(
            status__in=[PipelineRun.Status.QUEUED, PipelineRun.Status.RUNNING]
        ).exists():
            if time.monotonic() > deadline:
                raise CommandError("The edition's other jobs did not finish in time.")
            time.sleep(10)
