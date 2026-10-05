"""What a paid action will cost, shown on its button before anyone clicks.

Every estimate is deterministic arithmetic over the text the action would
send: the action's own window plan, about four characters to a token, the
system prompt it sends with every call, and an output allowance calibrated
against this service's ledger (tokens per call by purpose). Prices come from
the same tables the pipelines record actual cost with, so an estimate and the
AI spend panel speak the same dollars.

Only work still to do is priced: windows an earlier call already answered are
reused by the pipelines and cost nothing, so they are left out here too. An
estimate is a guide, not a quote; retries and escalations can add to it, and
its note says which.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from decimal import Decimal
from functools import cached_property

from almonium_book_processor.catalog.ai_translation import TRANSLATION_MODEL_PRICING
from almonium_book_processor.catalog.models import AIRun, Chapter, Edition, PipelineRun

CHARS_PER_TOKEN = 4
# Above this the button asks before it spends; below it the click just runs.
CONFIRM_ABOVE = Decimal("1.00")
BATCH_DISCOUNT = Decimal("0.5")

# Output tokens per call, reasoning included, from the ledger's averages.
GLOSS_OUTPUT_TOKENS = 150
ANALYSIS_OUTPUT_TOKENS = 1300
METADATA_OUTPUT_TOKENS = 400
ADVICE_OUTPUT_TOKENS = 700
# Output per input token where the answer grows with the text it reads.
ADAPTATION_OUTPUT_RATIO = 1.1
FIDELITY_OUTPUT_RATIO = 0.5
ALIGNMENT_OUTPUT_RATIO = 0.27
SUMMARY_OUTPUT_RATIO = 1.3
# JSON field names and ids around each block, beyond its text.
ENVELOPE_TOKENS_PER_BLOCK = 24


@dataclass(frozen=True)
class Estimate:
    """A price for one action, or the reason there is none."""

    usd: Decimal | None
    note: str = ""
    # What the confirmation names, e.g. "Generate 29 chapters".
    action: str = ""

    @property
    def label(self) -> str:
        if self.usd is None:
            return "AI"
        if self.usd == 0:
            return "$0"
        if self.usd < Decimal("0.01"):
            return "<$0.01"
        return f"~${self.usd.quantize(Decimal('0.01'))}"

    @property
    def confirm(self) -> str:
        if self.usd is None or self.usd < CONFIRM_ABOVE:
            return ""
        return f"{self.action or 'Run this'} for about ${self.usd.quantize(Decimal('0.01'))}?"


def unavailable(reason: str) -> Estimate:
    return Estimate(None, f"No estimate available: {reason}")


def tokens(chars: int) -> int:
    return math.ceil(chars / CHARS_PER_TOKEN)


def call_cost(pricing: dict, input_tokens: int, output_tokens: int, *, batch=False) -> Decimal:
    cost = (
        Decimal(input_tokens) * Decimal(pricing["input"])
        + Decimal(output_tokens) * Decimal(pricing["output"])
    ) / Decimal(1_000_000)
    return cost * BATCH_DISCOUNT if batch else cost


def _json_tokens(value) -> int:
    return tokens(len(json.dumps(value, ensure_ascii=False)))


def _answered(edition: Edition, hashes: list[str]) -> set[str]:
    """Window hashes an earlier call already answered; the pipelines reuse those."""
    return set(
        AIRun.objects.filter(
            edition=edition, status=AIRun.Status.SUCCEEDED, input_hash__in=hashes
        ).values_list("input_hash", flat=True)
    )


# Contextual glosses ---------------------------------------------------------


def gloss_chapter(chapter: Chapter, source: dict | None = None) -> Estimate:
    from almonium_book_processor.catalog.glosses import (
        SYSTEM_PROMPT,
        _windows,
        chapter_snapshot,
        explained_before,
    )

    try:
        source = source or chapter_snapshot(chapter)
    except ValueError as error:
        return unavailable(str(error))
    # Every window also carries the phrases noted earlier in the book.
    prompt = tokens(len(SYSTEM_PROMPT)) + _json_tokens(explained_before(chapter))
    pricing = TRANSLATION_MODEL_PRICING["quality"]
    windows = _windows(source)
    usd = sum(
        (call_cost(pricing, _json_tokens(w) + prompt, GLOSS_OUTPUT_TOKENS) for w in windows),
        Decimal(0),
    )
    return Estimate(usd, f"{len(windows)} call{'s' * (len(windows) != 1)} to the quality model.")


def gloss_book(chapters: list[tuple[Chapter, dict]]) -> Estimate:
    """The chapters still to generate, each with the snapshot it would send."""
    if not chapters:
        return Estimate(Decimal(0), "Every chapter is generated.")
    parts = [gloss_chapter(chapter, source) for chapter, source in chapters]
    usd = sum((part.usd or Decimal(0) for part in parts), Decimal(0))
    count = len(chapters)
    return Estimate(
        usd,
        f"{count} chapter{'s' * (count != 1)}, one quality-model call per 12,000 characters.",
        f"Generate {count} chapter{'s' * (count != 1)}",
    )


# Chapter analysis -----------------------------------------------------------


def chapter_analysis(edition: Edition) -> Estimate:
    from almonium_book_processor.catalog.chapter_analysis import edition_spec, snapshot

    spec = edition_spec(edition)
    try:
        plan = snapshot(edition, spec)
    except ValueError as error:
        return unavailable(str(error))
    windows = plan["windows"]
    if "panel" in spec:
        return _judges_estimate(edition, spec, windows)
    done = _answered(edition, [w["hash"] for w in windows])
    todo = [w for w in windows if w["hash"] not in done]
    prompt = tokens(len(spec["system_prompt"]))
    usd = sum(
        (
            call_cost(
                spec["pricing_per_million"],
                _json_tokens(w["data"]) + prompt,
                ANALYSIS_OUTPUT_TOKENS,
            )
            for w in todo
        ),
        Decimal(0),
    )
    if not todo:
        note = "Every window is already analyzed; results are reused."
    else:
        note = f"{len(todo)} of {len(windows)} windows to analyze; the rest are reused."
    return Estimate(usd, note, f"Analyze {len(todo)} windows")


def _judges_estimate(edition: Edition, spec: dict, windows: list[dict]) -> Estimate:
    """What the judges would cost: every judge reads each unread chapter ``readings`` times."""
    from almonium_book_processor.catalog.adaptation_wording import wording_judges

    read = wording_judges(edition)
    todo = [w for w in windows if w["data"]["chapter_id"] not in read]
    usd = sum(
        (
            spec["readings"]
            * call_cost(
                judge["pricing_per_million"],
                _json_tokens(w["data"]) + tokens(len(judge["system_prompt"])),
                ANALYSIS_OUTPUT_TOKENS,
            )
            for judge in spec["panel"]
            for w in todo
        ),
        Decimal(0),
    )
    chapters = len({w["data"]["chapter_id"] for w in todo})
    if not todo:
        note = "The judges have read every chapter as it stands; their readings are reused."
    else:
        note = (
            f"{chapters} chapter{'s' * (chapters != 1)} for {spec['model']} to read, "
            f"{spec['readings']} time{'s' * (spec['readings'] != 1)} each; the rest are reused."
        )
    return Estimate(usd, note, f"Analyze {chapters} chapter{'s' * (chapters != 1)}")


def _analysis_of_chars(chars: int) -> Decimal:
    """Difficulty analysis of text this long, as a judge or post-generation pass reads it."""
    from almonium_book_processor.ai.chapter_analysis import MAX_WINDOW_BYTES, SYSTEM_PROMPT

    windows = max(1, math.ceil(chars / MAX_WINDOW_BYTES))
    return windows * call_cost(
        TRANSLATION_MODEL_PRICING["draft"],
        tokens(chars) // windows + tokens(len(SYSTEM_PROMPT)),
        ANALYSIS_OUTPUT_TOKENS,
    )


# Adaptation -----------------------------------------------------------------


def _generation(chars: int, blocks: int, level: str, language: str) -> Decimal:
    from almonium_book_processor.ai.adaptation import pilot_prompt

    _, prompt = pilot_prompt(level, language)
    text = tokens(chars) + ENVELOPE_TOKENS_PER_BLOCK * blocks
    return call_cost(
        TRANSLATION_MODEL_PRICING["quality"],
        text + tokens(len(prompt)),
        math.ceil(text * ADAPTATION_OUTPUT_RATIO),
    )


def _fidelity(chars: int, blocks: int, tier: str | None = None) -> Decimal:
    from almonium_book_processor.ai.fidelity import SYSTEM_PROMPT
    from almonium_book_processor.catalog.fidelity_audit import audit_spec

    spec = audit_spec(tier)
    text = tokens(chars) + ENVELOPE_TOKENS_PER_BLOCK * blocks
    return call_cost(
        spec["pricing_per_million"],
        text + tokens(len(SYSTEM_PROMPT)),
        min(spec["max_output_tokens"], math.ceil(text * FIDELITY_OUTPUT_RATIO)),
    )


def _pilot_usd(chapter: Chapter, level: str, texts: list[str] | None = None) -> Decimal:
    """Generation, the blind difficulty judge and the fidelity audit of one chapter."""
    if texts is None:
        texts = [b.text for b in chapter.blocks.all()]
    chars = sum(len(text) for text in texts)
    return (
        _generation(chars, len(texts), level, chapter.edition.language)
        + _analysis_of_chars(chars)
        # The audit reads source and adaptation side by side.
        + _fidelity(2 * chars, len(texts))
    )


def pilot(chapter: Chapter, level: str, texts: list[str] | None = None) -> Estimate:
    from almonium_book_processor.catalog.adaptation import MAX_BLOCKS, MAX_CHARS

    if texts is None:
        texts = [b.text for b in chapter.blocks.all()]
    if not any(text.strip() for text in texts):
        return unavailable("the chapter has no text.")
    if len(texts) > MAX_BLOCKS or sum(len(text) for text in texts) > MAX_CHARS:
        return unavailable("the chapter is over the pilot limit of 100 blocks / 40,000 characters.")
    return Estimate(
        _pilot_usd(chapter, level, texts),
        "Generation, a blind difficulty judge and a fidelity audit of this chapter.",
    )


def probe(edition: Edition, level: str) -> Estimate:
    from almonium_book_processor.catalog.adaptation_floor import probe_sample

    try:
        sample = probe_sample(edition)
    except ValueError as error:
        return unavailable(str(error))
    usd = sum((_pilot_usd(chapter, level) for chapter in sample), Decimal(0))
    return Estimate(
        usd,
        f"{len(sample)} chapters, each generated, judged and audited.",
        f"Probe {level} on {len(sample)} chapters",
    )


def book_adaptation(
    edition: Edition, level: str, plan: dict | None = None, texts: dict | None = None
) -> Estimate:
    """Chunks not yet generated, then difficulty analysis of the new edition."""
    from almonium_book_processor.catalog.adaptation import digest
    from almonium_book_processor.catalog.book_adaptation import book_plan, generation_spec

    try:
        plan = plan or book_plan(edition)
        spec = generation_spec(level, edition.language)
    except ValueError as error:
        return unavailable(str(error))
    texts = texts if texts is not None else dict(edition.blocks.values_list("block_id", "text"))
    windows = plan["windows"]
    operation = "modernisation" if level in {"C1", "C2"} else f"{level.lower()}-book"
    # The run this click would resume, keyed exactly as queue_book keys it.
    previous = PipelineRun.objects.filter(
        idempotency_key=f"{edition.id}:{operation}:{digest([plan, spec])}"
    ).first()
    if previous and previous.status in {PipelineRun.Status.SUCCEEDED, PipelineRun.Status.RUNNING}:
        return Estimate(Decimal(0), "This edition is already generated or generating.")
    done = min(len(windows), previous.summary.get("completed") or 0) if previous else 0
    todo = windows[done:]
    chars = 0
    usd = Decimal(0)
    for window in todo:
        window_chars = sum(len(texts.get(block_id, "")) for block_id in window["block_ids"])
        chars += window_chars
        usd += _generation(window_chars, len(window["block_ids"]), level, edition.language)
    usd += _analysis_of_chars(chars)
    return Estimate(
        usd,
        f"{len(todo)} of {len(windows)} generation chunks, then difficulty analysis of the "
        "new edition. The fidelity audit is a separate click.",
        f"Generate {len(todo)} chunks of the {level} edition",
    )


def modernisation_advice() -> Estimate:
    from almonium_book_processor.catalog.modernisation import SYSTEM_PROMPT

    # Three chapters, three paragraphs each, at most 1,000 characters apiece.
    return Estimate(
        call_cost(
            TRANSLATION_MODEL_PRICING["quality"],
            tokens(9000 + len(SYSTEM_PROMPT)),
            ADVICE_OUTPUT_TOKENS,
        ),
        "One quality-model call over nine sample paragraphs.",
    )


def fidelity_audit(edition: Edition) -> Estimate:
    from almonium_book_processor.ai.fidelity import SYSTEM_PROMPT
    from almonium_book_processor.catalog.fidelity_audit import _json, audit_spec, edition_plan

    spec = audit_spec()
    try:
        plan = edition_plan(edition, spec)
    except ValueError as error:
        return unavailable(str(error))
    windows = plan["windows"]
    done = _answered(edition, [w["hash"] for w in windows])
    todo = [w for w in windows if w["hash"] not in done]
    prompt = tokens(len(SYSTEM_PROMPT))
    usd = Decimal(0)
    for window in todo:
        text = tokens(len(_json(window["data"])))
        usd += call_cost(
            spec["pricing_per_million"],
            text + prompt,
            min(spec["max_output_tokens"], math.ceil(text * FIDELITY_OUTPUT_RATIO)),
        )
    note = (
        "Every window is already audited; results are reused."
        if not todo
        else f"{len(todo)} of {len(windows)} windows to read; the rest are reused."
    )
    return Estimate(usd, note, f"Audit {len(todo)} windows")


# Metadata, translation and alignment ----------------------------------------


def metadata_detection(edition: Edition) -> Estimate:
    from almonium_book_processor.ai.metadata import (
        METADATA_EXCERPT_MAX_BLOCKS,
        METADATA_EXCERPT_MAX_CHARS,
        METADATA_SYSTEM_PROMPT,
    )
    from almonium_book_processor.catalog.metadata import METADATA_MODEL_PRICING

    texts = edition.blocks.exclude(text="").order_by("sequence").values_list("text", flat=True)
    chars = min(
        METADATA_EXCERPT_MAX_CHARS,
        sum(len(text) for text in texts[:METADATA_EXCERPT_MAX_BLOCKS]),
    )
    return Estimate(
        call_cost(
            METADATA_MODEL_PRICING,
            tokens(chars + len(METADATA_SYSTEM_PROMPT)),
            METADATA_OUTPUT_TOKENS,
        ),
        "One small call on the opening text; an unchanged repeat is free.",
    )


def translation(edition: Edition, tier: str, mode: str, usage: dict | None = None) -> Estimate:
    from almonium_book_processor.catalog.translation_jobs import price_edition

    usd = price_edition(edition, tier, batch=mode == "batch", usage=usage)
    return Estimate(
        usd,
        "One call per chapter; the title page and chapter descriptions follow at a few cents.",
        "Translate the whole book",
    )


def metadata_translation(edition: Edition) -> Estimate:
    from almonium_book_processor.catalog.metadata_translation import (
        chapter_inputs,
        title_page_inputs,
    )

    if not edition.source_edition_id:
        return unavailable("this edition has no source.")
    pricing = TRANSLATION_MODEL_PRICING["quality"]
    items = [title_page_inputs(edition), *(row["descriptions"] for row in chapter_inputs(edition))]
    usd = Decimal(0)
    for item in items:
        text = _json_tokens(item)
        usd += call_cost(pricing, text + 250, math.ceil(text * SUMMARY_OUTPUT_RATIO))
    return Estimate(usd, f"The title page and {len(items) - 1} chapter descriptions.")


def alignment_review(edition: Edition) -> Estimate:
    """Both texts read once, one request per chapter group, on the Batch API.

    The review aligns chapters locally first, so the groups may not exist yet
    when the button is drawn; the price follows the texts, one group per
    target chapter.
    """
    from almonium_book_processor.ai.alignment import ALIGNMENT_SYSTEM_PROMPT
    from almonium_book_processor.catalog.ai_alignment import MODEL_PRICING

    source = edition.inferred_alignment_source
    if source is None:
        return unavailable("this edition has no canonical text to align to.")
    chars, blocks = 0, 0
    for other in (source, edition):
        for text in other.blocks.exclude(text="").values_list("text", flat=True):
            chars += len(text)
            blocks += 1
    groups = edition.chapters.filter(blocks__isnull=False).distinct().count()
    if not groups:
        return unavailable("this edition has no text.")
    text = tokens(chars) + ENVELOPE_TOKENS_PER_BLOCK * blocks
    usd = call_cost(
        MODEL_PRICING["primary"],
        text + groups * tokens(len(ALIGNMENT_SYSTEM_PROMPT)),
        math.ceil(text * ALIGNMENT_OUTPUT_RATIO),
        batch=True,
    )
    return Estimate(
        usd,
        f"About {groups} chapter groups on the Batch API at half price. Groups that stay "
        "uncertain are escalated to the quality model, which is not included. A repeat "
        "on unchanged text is free.",
    )


class EditionEstimates:
    """The edition page's prices, each computed only when the template reads it."""

    def __init__(self, edition: Edition):
        self.edition = edition

    @cached_property
    def analysis(self) -> Estimate:
        return chapter_analysis(self.edition)

    @cached_property
    def detect(self) -> Estimate:
        return metadata_detection(self.edition)

    @cached_property
    def fidelity(self) -> Estimate:
        return fidelity_audit(self.edition)

    @cached_property
    def advice(self) -> Estimate:
        return modernisation_advice()

    @cached_property
    def metadata_translation(self) -> Estimate:
        return metadata_translation(self.edition)

    @cached_property
    def probe(self) -> dict[str, Estimate]:
        return {level: probe(self.edition, level) for level in ("B2", "B1")}

    @cached_property
    def book(self) -> dict[str, Estimate]:
        levels = ["B2", "B1"]
        if self.edition.cefr_level in {"C1", "C2"}:
            levels.append(self.edition.cefr_level)
        from almonium_book_processor.catalog.book_adaptation import book_plan

        try:
            plan = book_plan(self.edition)
        except ValueError as error:
            return {level: unavailable(str(error)) for level in levels}
        texts = dict(self.edition.blocks.values_list("block_id", "text"))
        return {level: book_adaptation(self.edition, level, plan, texts) for level in levels}

    @cached_property
    def _chapter_texts(self) -> list[tuple[Chapter, list[str]]]:
        return [
            (chapter, [b.text for b in sorted(chapter.blocks.all(), key=lambda b: b.sequence)])
            for chapter in self.edition.chapters.order_by("sequence").prefetch_related("blocks")
        ]

    def _pilots(self, level: str) -> dict[str, Estimate]:
        return {
            str(chapter.id): pilot(chapter, level, texts) for chapter, texts in self._chapter_texts
        }

    @cached_property
    def pilots(self) -> dict[str, dict[str, Estimate]]:
        """Per level, a price for each chapter the pilot select offers."""
        levels = ["B2", "B1"]
        if self.edition.cefr_level in {"C1", "C2"}:
            levels.append(self.edition.cefr_level)
        return {level: self._pilots(level) for level in levels}

    @cached_property
    def pilot(self) -> dict[str, Estimate]:
        """Per level, the price for the chapter the select starts on."""
        first = str(self._chapter_texts[0][0].id) if self._chapter_texts else None
        return {
            level: prices.get(first, unavailable("the edition has no chapters."))
            for level, prices in self.pilots.items()
        }

    @cached_property
    def translations(self) -> dict[str, Estimate]:
        from almonium_book_processor.catalog.translation_jobs import translation_usage

        counted = translation_usage(self.edition)
        return {
            f"{tier}|{mode}": translation(self.edition, tier, mode, counted)
            for tier in TRANSLATION_MODEL_PRICING
            for mode in ("direct", "batch")
        }

    @cached_property
    def translation(self) -> Estimate:
        """The form's initial choice: quality tier, direct."""
        return self.translations["quality|direct"]
