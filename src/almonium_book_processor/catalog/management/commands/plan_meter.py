from datetime import UTC, datetime

from django.conf import settings
from django.core.management.base import BaseCommand

from almonium_book_processor.ai.claude_code_provider import (
    claude_account,
    claude_config_dir,
    claude_meter,
)
from almonium_book_processor.ai.codex_provider import codex_home, codex_meter
from almonium_book_processor.ai.pricing import PLAN_WEEK_USD
from almonium_book_processor.catalog.models import PlanAccount, PlanMeterReading


def _instant(value):
    return datetime.fromisoformat(value) if value else None


class Command(BaseCommand):
    help = (
        "Read every plan account's weekly meter and what the used part of each week cost; "
        "with --record, keep the readings for the pages (the host's timer does this)."
    )

    def add_arguments(self, parser):
        parser.add_argument("--record", action="store_true")

    def handle(self, *args, **options):
        record = options["record"]
        answering = False
        for home in settings.CODEX_HOMES or [None]:
            account = codex_home(home)
            meter = codex_meter(home=account)
            if meter is None:
                self.stdout.write(
                    self.style.WARNING(f"The Codex meter of {account.name} could not be read.")
                )
                continue
            used = int(meter["used_percent"])
            answering = answering or used < 100
            spent = PLAN_WEEK_USD["codex"] * used / 100
            resets = datetime.fromtimestamp(meter["resets_at"], UTC)
            self.stdout.write(
                f"codex ({meter['plan_type']}, {account.name}): {used}% of the week used, "
                f"about ${spent:.2f} of ${PLAN_WEEK_USD['codex']:.2f}; "
                f"resets {resets.astimezone():%a %d %b %H:%M %Z}"
            )
            if record:
                PlanMeterReading.objects.create(
                    provider="codex",
                    account=account.name,
                    week_percent=used,
                    resets_at=resets,
                    plan_type=meter["plan_type"],
                )
                PlanAccount.objects.update_or_create(
                    provider="codex",
                    account=account.name,
                    defaults={"plan_label": meter["plan_type"] or ""},
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
            if record:
                PlanMeterReading.objects.create(
                    provider="claude-code",
                    account=account.name,
                    week_percent=week,
                    session_percent=claude.get("session_percent"),
                    fable_week_percent=fable,
                    resets_at=_instant(claude.get("week_resets_at")),
                    session_resets_at=_instant(claude.get("session_resets_at")),
                )
                who = claude_account(config_dir=account)
                PlanAccount.objects.update_or_create(
                    provider="claude-code",
                    account=account.name,
                    defaults={
                        key: value
                        for key, value in (
                            ("email", who.get("email")),
                            ("plan_label", who.get("plan")),
                        )
                        if value
                    },
                )
        if record and answering:
            # a Codex account answers: the books its used-up allowance held can go on
            from almonium_book_processor.catalog.production import requeue_held

            for run in requeue_held(allowance_only=True):
                self.stdout.write(f"{run.edition.slug}: started again after the allowance hold")
