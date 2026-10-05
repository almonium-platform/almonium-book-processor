"""Start a production: a source edition's adaptations made from probe to verdict by themselves.

./plan-manage produce shelley-frankenstein-en-orig --levels B2,B1 --follow
"""

import time

from django.core.management.base import BaseCommand, CommandError

from almonium_book_processor.catalog.models import Edition, PipelineRun
from almonium_book_processor.catalog.production import queue_production


class Command(BaseCommand):
    help = "Produce a source edition's adaptations without a person: probe to verdict."

    def add_arguments(self, parser):
        parser.add_argument("slug", help="The source edition, an original.")
        parser.add_argument("--levels", default="", help="Levels to adapt to, e.g. B2,B1.")
        parser.add_argument(
            "--languages", default="", help="Languages to translate into, e.g. uk,de."
        )
        parser.add_argument("--register", default="", help="The translations' literary register.")
        parser.add_argument(
            "--no-sign-off",
            action="store_true",
            help="Stop at the verdict and leave the review to a person.",
        )
        parser.add_argument(
            "--promote-to", default="", help="A configured promotion target; off unless named."
        )
        parser.add_argument(
            "--publish", action="store_true", help="With --promote-to: publish there as well."
        )
        parser.add_argument(
            "--follow", action="store_true", help="Print each step until it is finished."
        )

    def handle(self, *args, **options):
        edition = Edition.objects.filter(slug=options["slug"]).first()
        if edition is None:
            raise CommandError(f"No edition with the slug {options['slug']}.")
        try:
            run = queue_production(
                edition.id,
                [level.strip().upper() for level in options["levels"].split(",") if level.strip()],
                languages=options["languages"].split(","),
                register=options["register"],
                sign_off=not options["no_sign_off"],
                promote_to=options["promote_to"],
                publish=options["publish"],
            )
        except ValueError as error:
            raise CommandError(str(error)) from error
        made = [*run.summary["levels"], *run.summary.get("languages", [])]
        self.stdout.write(f"Production {run.id} of {', '.join(made)}.")
        if not options["follow"]:
            return
        shown = 0
        while True:
            run.refresh_from_db()
            for entry in run.summary["log"][shown:]:
                self.stdout.write(
                    f"{entry['at'][11:19]} {entry['level']} {entry['step']:8} {entry['note']}"
                )
            shown = len(run.summary["log"])
            self.stdout.flush()
            if run.status not in (PipelineRun.Status.QUEUED, PipelineRun.Status.RUNNING):
                break
            time.sleep(15)
        for level, outcome in run.summary["outcomes"].items():
            self.stdout.write(f"{level}: {outcome['outcome']}")
