"""Read the ledger for money paid twice; with --record, keep the report for the dashboard."""

from __future__ import annotations

from django.core.management.base import BaseCommand

from almonium_book_processor.catalog.spend_guard import guard_report, record_report


class Command(BaseCommand):
    help = "Report identical paid requests, twin editions, re-asked windows and purged paid text."

    def add_arguments(self, parser):
        parser.add_argument("--record", action="store_true", help="Keep the report for the pages.")

    def handle(self, *args, **options):
        report = guard_report()
        kept = record_report(report) if options["record"] else None
        self.stdout.write(
            f"Checked {report['checked_runs']} AI runs: {report['new_duplicate_calls']} call(s) "
            f"paid twice in the last {report['window_hours']} h (${report['new_duplicate_usd']}), "
            f"{report['total_duplicate_calls']} ever (${report['total_duplicate_usd']}); "
            f"{len(report['twins'])} twin edition group(s); {report['reasked_windows']} window(s) "
            f"re-asked; ${report['purged_usd']} of paid text purged in the window."
        )
        for twin in report["twins"]:
            self.stdout.write(self.style.WARNING(f"  twins: {', '.join(twin)}"))
        for entry in report["duplicates"][:5]:
            self.stdout.write(
                f"  x{entry['calls']} {entry['stage']}/{entry['version']} {entry['model']}"
                f" extra ${entry['extra_usd']}"
            )
        if kept is not None:
            self.stdout.write(f"Recorded as {kept.id}.")
