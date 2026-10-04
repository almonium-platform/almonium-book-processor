from django.core.management.base import BaseCommand, CommandError

from almonium_book_processor.catalog.ai_translation import (
    CODEX_TIER,
    SUBSCRIPTION_TIER,
    create_parallel_translation,
    run_translation_inline,
)
from almonium_book_processor.catalog.models import Edition


class Command(BaseCommand):
    help = (
        "Translate a canonical edition into a new parallel edition through the Claude Code or "
        "the Codex CLI on one of the owner's plans. Runs here, on the machine where the CLI is "
        "signed in; promote the result as a bundle."
    )

    def add_arguments(self, parser):
        parser.add_argument("source_slug", help="slug of the canonical edition to translate")
        parser.add_argument("target_language", help="language code of the translation, e.g. uk")
        parser.add_argument(
            "--register",
            default=Edition.LiteraryRegister.values[0],
            choices=Edition.LiteraryRegister.values,
        )
        parser.add_argument(
            "--through",
            default="claude-code",
            choices=["claude-code", "codex"],
            help="the CLI, and so the plan and the model, that writes the translation",
        )
        parser.add_argument(
            "--edition",
            help="slug of an existing empty parallel edition to fill instead of creating one",
        )

    def handle(self, *args, **options):
        try:
            source = Edition.objects.get(slug=options["source_slug"])
        except Edition.DoesNotExist as error:
            raise CommandError(f"No edition with slug {options['source_slug']}") from error
        tier = CODEX_TIER if options["through"] == "codex" else SUBSCRIPTION_TIER
        if options["edition"]:
            edition = Edition.objects.get(slug=options["edition"])
        else:
            edition = create_parallel_translation(
                source_edition=source,
                target_language=options["target_language"],
                register=options["register"],
                tier=tier,
            )
        self.stdout.write(f"Translating into {edition.slug} through {options['through']} ...")
        run = run_translation_inline(str(edition.id), tier=tier)
        # the run is completed under a lock on a fresh row; this instance is stale
        run.refresh_from_db()
        summary = (run.response_payload or {}).get("summary") or {}
        self.stdout.write(
            f"{run.status}: {summary.get('chapters', 0)} chapters, "
            f"{run.output_tokens} output tokens, edition {edition.slug}"
        )
        if run.error:
            self.stdout.write(self.style.WARNING(run.error[:1000]))
