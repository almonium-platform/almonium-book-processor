"""Have a model read the stretches offline sentence alignment left unconfirmed.

    ./plan-manage adjudicate_sentence_alignment --dry-run
    ./plan-manage adjudicate_sentence_alignment --sample 200
    ./plan-manage adjudicate_sentence_alignment --work <slug> --workers 4

Every aligned edition pair is read for its unconfirmed stretches; each stretch is bought
once (catalog/sentence_adjudication.py), so running this again asks only what is new and
writes whatever is already paid for. ``--sample`` spreads a fixed number of paragraphs
over the pairs, for a first look at what the model makes of them; ``--apply-only`` asks
nothing. A refused allowance stops the pass where it is.
"""

from __future__ import annotations

import hashlib
import random
from decimal import Decimal

from django.conf import settings
from django.core.management.base import BaseCommand

from almonium_book_processor.ai import gateway
from almonium_book_processor.catalog import sentence_adjudication as adjudication
from almonium_book_processor.catalog.models import PipelineRun
from almonium_book_processor.catalog.offline_sentence_alignment import processor_version

# The CLI's own instructions ride on every plan call, mostly cached (ai/codex_provider.py).
CALL_OVERHEAD_TOKENS = 15_000
CHARS_PER_TOKEN = 3


class Command(BaseCommand):
    help = "Adjudicate the unconfirmed stretches of offline sentence alignment with a model."

    def add_arguments(self, parser) -> None:
        parser.add_argument("--work", help="Only this work's slug.")
        parser.add_argument("--edition", help="Only pairs whose companion edition has this slug.")
        parser.add_argument(
            "--model", help="A model or seat instead of SENTENCE_ADJUDICATION_MODEL."
        )
        parser.add_argument(
            "--sample", type=int, help="This many paragraphs, spread over the pairs."
        )
        parser.add_argument("--seed", type=int, default=1, help="The sample's seed.")
        parser.add_argument("--workers", type=int, default=3, help="Calls in flight at once.")
        parser.add_argument(
            "--shard",
            help="i/n: only the works whose slug falls in part i of n, for several processes"
            " at once. A work is never split, so no two processes ask about the same book.",
        )
        parser.add_argument("--dry-run", action="store_true", help="Count and price; ask nothing.")
        parser.add_argument(
            "--apply-only", action="store_true", help="Write what is already paid for; ask nothing."
        )
        parser.add_argument(
            "--no-write", action="store_true", help="Buy judgments but write no artifacts."
        )

    def handle(self, *args, **options) -> None:
        setting = options["model"] or settings.SENTENCE_ADJUDICATION_MODEL
        seat = gateway.route(setting)
        runs = PipelineRun.objects.filter(
            stage=PipelineRun.Stage.ALIGN,
            status=PipelineRun.Status.SUCCEEDED,
            processor_version=processor_version(settings.SENTENCE_ALIGNMENT_MODEL),
        ).select_related("edition__work")
        if options["work"]:
            runs = runs.filter(edition__work__slug=options["work"])
        part, parts = (int(x) for x in (options["shard"] or "0/1").split("/"))

        def pairs():
            for run in sorted(
                adjudication.newest_runs(runs), key=lambda run: run.edition.work.slug
            ):
                slug = run.edition.work.slug
                if int(hashlib.sha256(slug.encode()).hexdigest(), 16) % parts != part:
                    continue
                try:
                    paragraphs = adjudication.paragraphs(run)
                except ValueError:
                    continue  # withdrawn, or no longer a complete pair
                if not paragraphs:
                    continue
                other = paragraphs[0].secondary.edition
                if options["edition"] and other.slug != options["edition"]:
                    continue
                yield run, other, paragraphs

        # a pair is read and judged before the next is read: the first call goes out at once
        work = pairs()
        if options["sample"] or options["dry_run"]:
            work = list(work)
        if options["sample"]:
            chooser = random.Random(options["seed"])
            share = max(1, -(-options["sample"] // max(1, len(work))))
            left = options["sample"]
            sampled = []
            for run, other, paragraphs in work:
                askable = [p for p in paragraphs if p.regions]
                chosen = chooser.sample(askable, min(share, len(askable), left))
                left -= len(chosen)
                if chosen:
                    sampled.append((run, other, chosen))
            work = sampled

        if options["dry_run"]:
            self._price(work, seat)
            return
        unavailable = gateway.unavailable(seat)
        if unavailable and not options["apply_only"]:
            self.stderr.write(unavailable)
            return
        total = adjudication.Tally()
        for run, other, paragraphs in work:
            tally = adjudication.adjudicate(
                paragraphs,
                model_setting=setting,
                edition_id=run.edition_id,
                workers=options["workers"],
                ask=not options["apply_only"],
                write=not options["no_write"],
            )
            total.add(tally)
            self.stdout.write(
                f"{other.slug}: {tally.regions} stretch(es) in {tally.paragraphs} paragraph(s);"
                f" {tally.found} already paid, {tally.mended} mended, {tally.answered} answered in"
                f" {tally.calls} call(s),"
                f" {tally.unusable} unusable, {tally.written} artifact(s) written"
            )
            self.stdout.flush()
            if tally.held:
                self.stdout.write(f"Held: {tally.held}")
                break
        self._report(total, seat)

    def _price(self, work, seat) -> None:
        model = seat.model
        regions = {}
        oversized = paragraphs = 0
        for _, _, items in work:
            paragraphs += len(items)
            for paragraph in items:
                oversized += paragraph.oversized
                for region in paragraph.regions:
                    regions.setdefault(region.identity(model), region)
        history = adjudication.judgment_history(regions, model)
        pending = {
            identity: region
            for identity, region in regions.items()
            if adjudication.needs_judgment(history[identity])
        }
        calls = len(adjudication._packs(pending))
        chars = sum(region.chars for region in pending.values())
        clauses = sum(len(r.primary) + len(r.secondary) for r in pending.values())
        prices = gateway.prices(seat)
        fresh = chars / CHARS_PER_TOKEN + clauses * 8 + calls * 700
        cached = calls * CALL_OVERHEAD_TOKENS if seat.on_plan else 0
        output = clauses * 12 + calls * 300
        usd = (
            Decimal(fresh) * Decimal(prices["input"])
            + Decimal(cached) * Decimal(prices["cached_input"])
            + Decimal(output) * Decimal(prices["output"])
        ) / 1_000_000
        self.stdout.write(
            f"{len(work)} edition pair(s), {paragraphs} paragraph(s), {len(regions)} distinct"
            f" stretch(es), {oversized} too long to ask."
        )
        self.stdout.write(
            f"{len(regions) - len(pending)} already paid or given up; {len(pending)} to ask in"
            f" about {calls} call(s) on {seat.provider}:{model}, about ${usd:.2f}"
            + (" of the plan." if seat.on_plan else ".")
        )

    def _report(self, tally, seat) -> None:
        write = self.stdout.write
        write("")
        write(f"On {seat.provider}:{seat.model}: {tally.calls} call(s), {tally.reread} read again")
        write(
            f"Stretches: {tally.regions} ({tally.oversized} more too long to ask);"
            f" {tally.found} already paid ({tally.mended} of them mended from a paid answer),"
            f" {tally.answered} answered, {tally.unusable} unusable,"
            f" {tally.given_up} given up, {tally.in_flight} call(s) in flight elsewhere"
        )
        if tally.after_groups:
            write(
                f"In the judged stretches: {tally.before_groups} unconfirmed group(s) became"
                f" {tally.after_groups}, {tally.after_certain} of them confirmed"
                f" ({100 * tally.after_certain // tally.after_groups}%);"
                f" {tally.reordered} stretch(es) pair clauses out of order"
            )
        write(f"Artifacts written: {tally.written}; text changed meanwhile: {tally.changed_text}")
        for error in sorted(set(tally.errors)):
            write(f"  failed call: {error} x{tally.errors.count(error)}")
        if tally.held:
            write(f"Held, nothing lost: {tally.held}. Run again to go on.")
