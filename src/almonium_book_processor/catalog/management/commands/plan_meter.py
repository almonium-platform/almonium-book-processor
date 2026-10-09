from datetime import UTC, datetime

from django.conf import settings
from django.core.management.base import BaseCommand

from almonium_book_processor.ai.claude_code_provider import claude_config_dir, claude_meter
from almonium_book_processor.ai.codex_provider import codex_home, codex_meter
from almonium_book_processor.ai.pricing import PLAN_WEEK_USD


class Command(BaseCommand):
    help = "Read every plan account's weekly meter and what the used part of each week cost."

    def handle(self, *args, **options):
        for home in settings.CODEX_HOMES or [None]:
            account = codex_home(home)
            meter = codex_meter(home=account)
            if meter is None:
                self.stdout.write(
                    self.style.WARNING(f"The Codex meter of {account.name} could not be read.")
                )
                continue
            used = meter["used_percent"]
            spent = PLAN_WEEK_USD["codex"] * int(used) / 100
            resets = datetime.fromtimestamp(meter["resets_at"], UTC).astimezone()
            self.stdout.write(
                f"codex ({meter['plan_type']}, {account.name}): {used:.0f}% of the week used, "
                f"about ${spent:.2f} of ${PLAN_WEEK_USD['codex']:.2f}; "
                f"resets {resets:%a %d %b %H:%M %Z}"
            )
        for config_dir in settings.CLAUDE_CONFIG_DIRS or [None]:
            account = claude_config_dir(config_dir)
            claude = claude_meter(config_dir=account)
            if claude is None:
                self.stdout.write(
                    self.style.WARNING(f"The Claude meter of {account.name} could not be read.")
                )
                continue
            week = claude["week_percent"]
            spent = PLAN_WEEK_USD["claude-code"] * week / 100
            fable = claude.get("fable_week_percent")
            self.stdout.write(
                f"claude-code ({account.name}): {week}% of the week used by every session of "
                f"the account, about ${spent:.2f} of ${PLAN_WEEK_USD['claude-code']:.2f}"
                + (f"; Fable's own week {fable}%" if fable is not None else "")
            )
