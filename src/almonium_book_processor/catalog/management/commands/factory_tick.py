from django.core.management.base import BaseCommand

from almonium_book_processor.catalog.factory import tick


class Command(BaseCommand):
    help = (
        "One pass of the factory: report every book under way to Almonium, then start the "
        "next wanted book if the plans have room (the host's timer runs this every 15 minutes)."
    )

    def handle(self, *args, **options):
        result = tick()
        self.stdout.write(
            f"reported {result.get('reported', 0)}, under way {result.get('under_way', 0)}, "
            f"started {result['started'] or 'nothing'}: {result['reason']}"
        )
