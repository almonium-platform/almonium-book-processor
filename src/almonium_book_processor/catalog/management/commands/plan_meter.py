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
from almonium_book_processor.catalog.plan_pause import pause_on_limit, seed_priorities


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
        if record:
            # the settings' order is where the dashboard's order of the accounts starts
            seed_priorities("codex", [codex_home(home).name for home in settings.CODEX_HOMES])
            seed_priorities(
                "claude-code",
                [claude_config_dir(path).name for path in settings.CLAUDE_CONFIG_DIRS],
            )
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
                if pause_on_limit("codex", account.name, used):
                    self.stdout.write(f"codex ({account.name}): paused at its limit")
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
                if pause_on_limit(
                    "claude-code",
                    account.name,
                    week,
                    session_percent=claude.get("session_percent"),
                ):
                    self.stdout.write(f"claude-code ({account.name}): paused at its limit")
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
        if "antigravity" in {plan.strip() for plan in settings.AI_PLANS.split(",")}:
            from almonium_book_processor.ai.antigravity_provider import (
                ACCOUNT,
                antigravity_meter,
            )

            gemini = antigravity_meter()
            if gemini is None:
                self.stdout.write(self.style.WARNING("The Gemini plan's meter could not be read."))
            else:
                week = gemini["week_percent"]
                spent = PLAN_WEEK_USD["antigravity"] * week / 100
                self.stdout.write(
                    f"antigravity ({ACCOUNT}): {week}% of the Gemini models' week used, about "
                    f"${spent:.2f} of ${PLAN_WEEK_USD['antigravity']:.2f}; "
                    f"session {gemini.get('session_percent', 0)}%"
                )
                if record:
                    if pause_on_limit(
                        "antigravity",
                        ACCOUNT,
                        week,
                        session_percent=gemini.get("session_percent"),
                    ):
                        self.stdout.write(f"antigravity ({ACCOUNT}): paused at its limit")
                    PlanMeterReading.objects.create(
                        provider="antigravity",
                        account=ACCOUNT,
                        week_percent=week,
                        session_percent=gemini.get("session_percent"),
                        resets_at=gemini.get("week_resets_at"),
                        session_resets_at=gemini.get("session_resets_at"),
                        plan_type="AI Ultra",
                    )
                    PlanAccount.objects.get_or_create(
                        provider="antigravity",
                        account=ACCOUNT,
                        defaults={"plan_label": "AI Ultra"},
                    )
        from almonium_book_processor.ai.elevenlabs_meter import (
            ACCOUNT as ELEVENLABS_ACCOUNT,
        )
        from almonium_book_processor.ai.elevenlabs_meter import (
            elevenlabs_api_key,
            elevenlabs_meter,
        )

        if elevenlabs_api_key():
            eleven = elevenlabs_meter()
            if eleven is None:
                self.stdout.write(self.style.WARNING("The ElevenLabs meter could not be read."))
            else:
                used = eleven["used_percent"]
                resets = eleven["resets_at"]
                reset_note = f"; resets {resets.astimezone():%a %d %b %H:%M %Z}" if resets else ""
                self.stdout.write(
                    f"elevenlabs ({eleven['plan_type'] or 'api'}): {used}% of the month used, "
                    f"{eleven['units_used']:,} of {eleven['units_limit']:,} chars{reset_note}"
                )
                if record:
                    PlanMeterReading.objects.create(
                        provider="elevenlabs",
                        account=ELEVENLABS_ACCOUNT,
                        week_percent=used,
                        units_used=eleven["units_used"],
                        units_limit=eleven["units_limit"],
                        resets_at=resets,
                        plan_type=eleven["plan_type"],
                    )
                    defaults = {
                        key: value
                        for key, value in (
                            ("plan_label", eleven["plan_label"]),
                            ("renews_on", eleven["renews_on"]),
                        )
                        if value
                    }
                    PlanAccount.objects.update_or_create(
                        provider="elevenlabs",
                        account=ELEVENLABS_ACCOUNT,
                        defaults=defaults,
                    )
        if record and answering:
            # a Codex account answers: the books its used-up allowance held can go on
            from almonium_book_processor.ai import claude_code_provider, codex_provider
            from almonium_book_processor.catalog.plan_pause import (
                open_claude_accounts,
                open_codex_accounts,
            )
            from almonium_book_processor.catalog.production import requeue_held

            # a book held because no account of a plan was open waits until one is again
            waiting = tuple(
                words
                for words, open_now in (
                    (claude_code_provider.EVERY_ACCOUNT_PAUSED, open_claude_accounts()),
                    (codex_provider.EVERY_ACCOUNT_PAUSED, open_codex_accounts()),
                )
                if not open_now
            )
            for run in requeue_held(allowance_only=True, not_held_for=waiting):
                self.stdout.write(f"{run.edition.slug}: started again after the allowance hold")
