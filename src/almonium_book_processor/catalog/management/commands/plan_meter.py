from datetime import UTC, datetime

from django.core.management.base import BaseCommand

from almonium_book_processor.ai.codex_provider import codex_meter
from almonium_book_processor.ai.pricing import PLAN_WEEK_USD


class Command(BaseCommand):
    help = (
        "Read the Codex plan's weekly meter and what the used part of the week cost. The Claude "
        "Code CLI exposes no meter; read that one in its /usage screen."
    )

    def handle(self, *args, **options):
        meter = codex_meter()
        if meter is None:
            self.stdout.write(self.style.WARNING("The Codex meter could not be read."))
            return
        used = meter["used_percent"]
        spent = PLAN_WEEK_USD["codex"] * int(used) / 100
        resets = datetime.fromtimestamp(meter["resets_at"], UTC).astimezone()
        self.stdout.write(
            f"codex ({meter['plan_type']}): {used:.0f}% of the week used, "
            f"about ${spent:.2f} of ${PLAN_WEEK_USD['codex']:.2f}; "
            f"resets {resets:%a %d %b %H:%M %Z}"
        )
