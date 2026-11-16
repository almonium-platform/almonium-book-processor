"""Run on the host every five minutes: make the entry writers match the Operations page.

./plan-manage lexicon_writers --reconcile
"""

from django.core.management.base import BaseCommand

from almonium_book_processor.catalog.lexicon_writers import reconcile


class Command(BaseCommand):
    help = "Start the entry writers switched on on the Operations page and stop the others."

    def add_arguments(self, parser):
        parser.add_argument("--reconcile", action="store_true", help="Act on the host.")

    def handle(self, *args, **options):
        if not options["reconcile"]:
            self.stdout.write("Nothing done; pass --reconcile on the host that writes the entries.")
            return
        for line in reconcile():
            self.stdout.write(line)
