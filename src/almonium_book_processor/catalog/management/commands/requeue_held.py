from django.core.management.base import BaseCommand

from almonium_book_processor.catalog.production import requeue_held


class Command(BaseCommand):
    help = (
        "Start again the productions held by circumstance: a step that broke too often, a "
        "plan whose allowance ran out, a worker that died under them. With --allowance only "
        "the allowance holds, which the meter's timer does once a plan account answers again."
    )

    def add_arguments(self, parser):
        parser.add_argument("--allowance", action="store_true")

    def handle(self, *args, **options):
        started = requeue_held(allowance_only=options["allowance"])
        for run in started:
            self.stdout.write(f"{run.edition.slug}: production {run.id} started again")
        self.stdout.write(f"{len(started)} production(s) started again.")
