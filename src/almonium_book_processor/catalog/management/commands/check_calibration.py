"""Validate calibration fixtures and compare saved predictions without paid calls."""

import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from pydantic import ValidationError

from almonium_book_processor.processing.calibration import FixtureSet, PredictionSet, compare


class Command(BaseCommand):
    help = "Validate difficulty fixtures and compare saved predictions, offline and read-only."
    requires_system_checks = []

    def add_arguments(self, parser):
        parser.add_argument("fixtures", type=Path)
        parser.add_argument("--predictions", type=Path)

    def handle(self, *args, **options):
        try:
            fixtures = FixtureSet.model_validate_json(
                options["fixtures"].read_text(encoding="utf-8")
            )
            predictions = (
                PredictionSet.model_validate_json(
                    options["predictions"].read_text(encoding="utf-8")
                )
                if options["predictions"]
                else PredictionSet(schema_version=1, predictions=[])
            )
            report = compare(fixtures, predictions)
        except ValidationError as error:
            raise CommandError(
                f"Invalid calibration schema ({error.error_count()} errors)."
            ) from None
        except (OSError, UnicodeError, ValueError) as error:
            raise CommandError(str(error)) from None
        self.stdout.write(json.dumps(report, ensure_ascii=False, indent=2))
