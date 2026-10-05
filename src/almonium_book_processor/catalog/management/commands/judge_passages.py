"""Have the level judges read the owner's calibration passages and compare.

    ./plan-manage judge_passages

Each passage is read once by every configured judge, an adaptation's for its wording and an
original's by the whole rubric, as a chapter of that edition would be. What they read is kept
in the file beside the owner's own level, and a passage already read costs nothing.
"""

import json
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from almonium_book_processor.catalog.adaptation_wording import reads_wording, text_hash
from almonium_book_processor.catalog.chapter_projections import LEVELS
from almonium_book_processor.catalog.models import Edition
from almonium_book_processor.catalog.pilot_difficulty import judge_specs, judge_text

FILE = Path(settings.BASE_DIR) / "calibration" / "level_passages.json"
VERSION = "level-calibration-v1"


class Command(BaseCommand):
    help = "Read the calibration passages with the level judges and compare with the owner."

    def add_arguments(self, parser):
        parser.add_argument("--file", default=str(FILE))

    def handle(self, *args, **options):
        if not settings.DIFFICULTY_JUDGES:
            raise CommandError("Set DIFFICULTY_JUDGES: there is no judge to calibrate.")
        path = Path(options["file"])
        document = json.loads(path.read_text())
        gaps = []
        for passage in document["passages"]:
            edition = Edition.objects.get(slug=passage["edition"])
            block = edition.blocks.select_related("chapter").get(block_id=passage["block_id"])
            blocks = [
                {"block_id": block.block_id, "text": passage["text"], "type": block.block_type}
            ]
            read = {}
            for spec in judge_specs(edition.language, wording=reads_wording(edition)):
                verdict = judge_text(
                    edition=edition,
                    key=f"calibration:{passage['id']}",
                    seed=text_hash(blocks),
                    summary={"calibration": passage["id"]},
                    chapter_sequence=block.chapter.sequence,
                    blocks=blocks,
                    spec=spec,
                    readings=1,
                    provider=None,
                    processor_version=VERSION,
                )
                read[spec["model"]] = verdict["max_level"]
            passage["judges"] = read
            owner = passage.get("owner_level")
            line = f"{passage['id']:4} " + "  ".join(f"{m}: {level}" for m, level in read.items())
            if owner in LEVELS:
                line += f"  | owner: {owner}"
                gaps += [LEVELS.index(level) - LEVELS.index(owner) for level in read.values()]
            self.stdout.write(line)
        path.write_text(json.dumps(document, ensure_ascii=False, indent=1) + "\n")
        if gaps:
            exact = sum(gap == 0 for gap in gaps)
            self.stdout.write(
                f"Against the owner: {exact} of {len(gaps)} readings the same level, "
                f"{sum(gap > 0 for gap in gaps)} higher, {sum(gap < 0 for gap in gaps)} lower."
            )
        else:
            self.stdout.write("No owner levels yet: fill owner_level in the file to compare.")
