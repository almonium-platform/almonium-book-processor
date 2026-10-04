from django.core.management.base import BaseCommand, CommandError

from almonium_book_processor.catalog.ai_translation import (
    SUBSCRIPTION_TIER,
    create_parallel_translation,
    run_translation_inline,
)
from almonium_book_processor.catalog.models import Edition


class Command(BaseCommand):
    help = (
        "Translate a canonical edition into a new parallel edition through the Claude Code CLI "
        "on the owner's subscription. Runs here, on the machine where the CLI is signed in; "
        "promote the result as a bundle."
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
            "--edition",
            help="slug of an existing empty parallel edition to fill instead of creating one",
        )

    def handle(self, *args, **options):
        try:
            source = Edition.objects.get(slug=options["source_slug"])
        except Edition.DoesNotExist as error:
            raise CommandError(f"No edition with slug {options['source_slug']}") from error
        if options["edition"]:
            edition = Edition.objects.get(slug=options["edition"])
        else:
            edition = create_parallel_translation(
                source_edition=source,
                target_language=options["target_language"],
                register=options["register"],
                tier=SUBSCRIPTION_TIER,
            )
        self.stdout.write(f"Translating into {edition.slug} through Claude Code ...")
        run = run_translation_inline(str(edition.id), tier=SUBSCRIPTION_TIER)
        summary = (run.response_payload or {}).get("summary") or {}
        self.stdout.write(
            f"{run.status}: {summary.get('chapters', 0)} chapters, "
            f"{run.output_tokens} output tokens, edition {edition.slug}"
        )
        if run.error:
            self.stdout.write(self.style.WARNING(run.error[:1000]))
