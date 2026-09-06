"""Bibliographic metadata for private imports: header first, one small AI call second.

A private import no longer needs the owner to type title, author, language, a
blurb, or a year before uploading. The file header supplies most of it
deterministically; a single structured call then verifies those values against
the opening text and adds what a file cannot carry. Values the owner typed at
upload are never overridden, and everything else is a proposal the owner
confirms or edits in Almonium.
"""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from decimal import Decimal
from typing import Any

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django.utils.text import slugify

from almonium_book_processor import __version__
from almonium_book_processor.ai.metadata import (
    METADATA_EXCERPT_MAX_BLOCKS,
    METADATA_EXCERPT_MAX_CHARS,
    METADATA_OUTPUT_SCHEMA,
    METADATA_SYSTEM_PROMPT,
    METADATA_USER_TEMPLATE,
    BookMetadataProposal,
)
from almonium_book_processor.ai.openai_provider import OpenAIBatchProvider, response_output_text
from almonium_book_processor.catalog.models import (
    METADATA_FIELD_LABELS,
    AIRun,
    ContentBlock,
    Edition,
    ModelConfiguration,
    PipelineRun,
    PromptTemplate,
)
from almonium_book_processor.languages import LANGUAGES, normalize_language_code
from almonium_book_processor.models import EditionMetadata

logger = logging.getLogger(__name__)

PROMPT_NAME = "private-import-metadata"
PROMPT_VERSION = 1

METADATA_FIELDS = tuple(METADATA_FIELD_LABELS)

PROVENANCE_USER = "user"
PROVENANCE_SOURCE = "source"
PROVENANCE_AI = "ai"

# A catalogue upload without pinned slugs gets these until its title is known;
# the metadata stage replaces them, and publication refuses to ship them.
PROVISIONAL_SLUG_PREFIX = "pending-"

EDITION_SLUG_SUFFIXES = {
    Edition.EditionType.ORIGINAL: "original",
    Edition.EditionType.HUMAN_TRANSLATION: "human",
    Edition.EditionType.MACHINE_TRANSLATION: "machine",
    Edition.EditionType.ADAPTATION: "adapted",
    Edition.EditionType.ABRIDGEMENT: "abridged",
}


# The review panel names some fields after the model they live on, so its field
# names are not the provenance keys. Work title and language are the edition's
# too whenever the edition owns its work.
METADATA_FORM_FIELDS = {
    "work_title": "title",
    "author": "author",
    "description": "description",
    "original_language": "language",
    "publication_year": "publication_year",
    "work_slug": "work_slug",
    "edition_slug": "edition_slug",
    "cover_url": "cover_url",
}


def provisional_slug() -> str:
    return f"{PROVISIONAL_SLUG_PREFIX}{uuid.uuid4().hex[:12]}"


def has_provisional_slug(edition: Edition) -> bool:
    return edition.slug.startswith(PROVISIONAL_SLUG_PREFIX) or edition.work.slug.startswith(
        PROVISIONAL_SLUG_PREFIX
    )


def _edition_owns_work(edition: Edition) -> bool:
    """Only the original edition (or the first one) may describe the work itself."""

    return edition.edition_type == Edition.EditionType.ORIGINAL or not edition.work.title


# The draft translation tier: one call of a few thousand tokens per book.
METADATA_MODEL_PRICING = {"input": "0.20", "cached_input": "0.02", "output": "1.20"}


def initial_provenance(**fields: object) -> dict[str, str]:
    """Mark the fields the owner filled in at upload; the rest are detected later."""

    return {name: PROVENANCE_USER for name, value in fields.items() if value not in (None, "")}


def form_provenance(edition: Edition) -> dict[str, str]:
    """Metadata provenance keyed by the review form's field names."""

    provenance = edition.work.metadata_provenance
    fields = dict(METADATA_FORM_FIELDS)
    if _edition_owns_work(edition):
        # The same decision named the work and this edition.
        fields["edition_title"] = "title"
        fields["language"] = "language"
    return {name: provenance[key] for name, key in fields.items() if provenance.get(key)}


def adopt_source_metadata(edition: Edition, declared: EditionMetadata) -> None:
    """Fill the fields the owner left blank from what the file header declares."""

    work = edition.work
    provenance = dict(work.metadata_provenance)
    owns_work = _edition_owns_work(edition)
    if not edition.title:
        edition.title = declared.title[:500]
        if owns_work and not work.title:
            work.title = edition.title
            provenance["title"] = PROVENANCE_SOURCE
    if not edition.author:
        edition.author = declared.author[:300]
        if owns_work and not work.author:
            work.author = edition.author
            provenance["author"] = PROVENANCE_SOURCE
    if not edition.language:
        edition.language = declared.language
        if owns_work and not work.original_language:
            work.original_language = edition.language
            provenance["language"] = PROVENANCE_SOURCE
    work.metadata_provenance = provenance
    edition.save(update_fields=["title", "author", "language", "updated_at"])
    work.save(
        update_fields=["title", "author", "original_language", "metadata_provenance", "updated_at"]
    )


def detect_metadata(edition_id: str) -> PipelineRun:
    """Run the metadata stage for an ingested edition.

    Header values are already on the edition. When an OpenAI key is configured
    the stage verifies them against the opening text and proposes a blurb and
    a first-publication year; without one it only marks detection finished so
    the owner is asked to confirm what the header said.
    """

    edition = Edition.objects.select_related("work").get(id=edition_id)
    ai_enabled = bool(settings.OPENAI_API_KEY)
    # Keyed by the source and what the owner typed, not by the current values:
    # adopting a proposal must not make a retry look like new input.
    input_hash = hashlib.sha256(
        json.dumps(
            {
                "source_sha256": edition.source_sha256,
                "ai": settings.OPENAI_METADATA_MODEL if ai_enabled else "",
                "prompt_version": PROMPT_VERSION,
                "owner_supplied": _owner_supplied(edition),
            },
            sort_keys=True,
        ).encode()
    ).hexdigest()
    run, _ = PipelineRun.objects.get_or_create(
        idempotency_key=f"{edition.id}:{input_hash}:metadata:{__version__}",
        defaults={
            "edition": edition,
            "stage": PipelineRun.Stage.METADATA,
            "processor_version": __version__,
            "input_hash": input_hash,
        },
    )
    if run.status == PipelineRun.Status.SUCCEEDED:
        return run

    run.status = PipelineRun.Status.RUNNING
    run.started_at = timezone.now()
    run.error = ""
    run.save(update_fields=["status", "started_at", "error", "updated_at"])

    work = edition.work
    provenance = dict(work.metadata_provenance)
    proposal = None
    ai_run = None
    open_fields = [name for name in METADATA_FIELDS if provenance.get(name) != PROVENANCE_USER]
    if ai_enabled and open_fields:
        # A failed or unavailable model call must not fail the import: the
        # header values remain and the owner is still asked to confirm them.
        try:
            ai_run = _propose_with_ai(edition, run)
        except Exception:
            logger.exception("Metadata proposal failed for edition %s", edition.id)
        if ai_run is not None and ai_run.status == AIRun.Status.SUCCEEDED:
            proposal = BookMetadataProposal.model_validate(ai_run.response_payload["proposal"])
    if proposal is not None:
        _apply_proposal(edition, proposal, provenance)
    _finalize_slugs(edition, provenance)

    with transaction.atomic():
        work.metadata_provenance = provenance
        work.metadata_detected_at = timezone.now()
        work.save(
            update_fields=[
                "slug",
                "title",
                "author",
                "description",
                "original_language",
                "publication_year",
                "metadata_provenance",
                "metadata_detected_at",
                "updated_at",
            ]
        )
        edition.save(update_fields=["slug", "title", "author", "language", "updated_at"])
        run.status = PipelineRun.Status.SUCCEEDED
        run.progress = 100
        run.finished_at = timezone.now()
        run.summary = {
            "ai_enabled": ai_enabled,
            "open_fields": open_fields,
            "ai_run_id": str(ai_run.id) if ai_run else None,
            "ai_status": ai_run.status if ai_run else None,
            "provenance": provenance,
        }
        run.save(update_fields=["status", "progress", "finished_at", "summary", "updated_at"])
    return run


def confirm_metadata(
    edition: Edition,
    *,
    title: str | None = None,
    author: str | None = None,
    description: str | None = None,
    language: str | None = None,
    publication_year: int | None = None,
    clear_publication_year: bool = False,
    work_title: str | None = None,
    original_language: str | None = None,
    work_slug: str | None = None,
    edition_slug: str | None = None,
    cover_url: str | None = None,
    cefr_level: str | None = None,
    clear_cefr_level: bool = False,
) -> bool:
    """Apply confirmed values; return whether the edition's language changed.

    ``title``/``author``/``language`` describe the edition and, when the edition
    owns its work, the work too; ``work_title``/``original_language`` address
    the work explicitly. A changed language invalidates sentence splitting and
    lexical analysis, so a ready edition is sent back through the NLP stages.
    The stage keys include the language, so this never repeats work already
    done for it.
    """

    work = edition.work
    owns_work = _edition_owns_work(edition)
    provenance = dict(work.metadata_provenance)
    language_changed = False
    if title is not None and title.strip():
        edition.title = title.strip()[:500]
        if owns_work and work_title is None:
            work.title = edition.title
        provenance["title"] = PROVENANCE_USER
    if work_title is not None and work_title.strip():
        work.title = work_title.strip()[:500]
        provenance["title"] = PROVENANCE_USER
    if author is not None and author.strip():
        edition.author = author.strip()[:300]
        if owns_work:
            work.author = edition.author
        provenance["author"] = PROVENANCE_USER
    if description is not None:
        work.description = description.strip()
        provenance["description"] = PROVENANCE_USER
    if language and language != edition.language:
        edition.language = language
        if owns_work and original_language is None:
            work.original_language = language
        provenance["language"] = PROVENANCE_USER
        language_changed = True
    if original_language:
        work.original_language = original_language
        provenance["language"] = PROVENANCE_USER
    if publication_year is not None or clear_publication_year:
        work.publication_year = publication_year
        provenance["publication_year"] = PROVENANCE_USER
    if work_slug:
        work.slug = work_slug
        provenance["work_slug"] = PROVENANCE_USER
    if edition_slug:
        edition.slug = edition_slug
        provenance["edition_slug"] = PROVENANCE_USER
    if cover_url is not None:
        work.cover_url = cover_url.strip()
        provenance["cover_url"] = PROVENANCE_USER
    if cefr_level or clear_cefr_level:
        edition.cefr_level = cefr_level or None
    work.metadata_provenance = provenance
    work.metadata_confirmed_at = timezone.now()

    with transaction.atomic():
        work.save(
            update_fields=[
                "slug",
                "title",
                "author",
                "description",
                "original_language",
                "publication_year",
                "cover_url",
                "metadata_provenance",
                "metadata_confirmed_at",
                "updated_at",
            ]
        )
        if language_changed and edition.status == Edition.Status.READY:
            from almonium_book_processor.catalog.tasks import process_normalized_edition

            edition.status = Edition.Status.PROCESSING
            transaction.on_commit(lambda: process_normalized_edition.delay(str(edition.id)))
        edition.save(
            update_fields=[
                "slug",
                "title",
                "author",
                "language",
                "cefr_level",
                "status",
                "updated_at",
            ]
        )
    return language_changed


def _unique_slug(model, base: str, *, exclude_id) -> str:
    base = base[:150] or "book"
    candidate = base
    counter = 2
    while model.objects.filter(slug=candidate).exclude(id=exclude_id).exists():
        candidate = f"{base}-{counter}"
        counter += 1
    return candidate


def _finalize_slugs(edition: Edition, provenance: dict[str, str]) -> None:
    """Replace provisional slugs with ones derived from the detected metadata."""

    from almonium_book_processor.catalog.models import Work

    work = edition.work
    if not edition.title:
        edition.title = work.title
    if (
        work.slug.startswith(PROVISIONAL_SLUG_PREFIX)
        and provenance.get("work_slug") != PROVENANCE_USER
        and work.title
    ):
        work.slug = _unique_slug(Work, slugify(work.title), exclude_id=work.id)
    if (
        edition.slug.startswith(PROVISIONAL_SLUG_PREFIX)
        and provenance.get("edition_slug") != PROVENANCE_USER
        and not work.slug.startswith(PROVISIONAL_SLUG_PREFIX)
        and edition.language
    ):
        suffix = EDITION_SLUG_SUFFIXES.get(edition.edition_type, edition.edition_type)
        edition.slug = _unique_slug(
            Edition, f"{work.slug}-{edition.language}-{suffix}", exclude_id=edition.id
        )


def _owner_supplied(edition: Edition) -> dict[str, object]:
    work = edition.work
    values = {
        "title": edition.title,
        "author": edition.author,
        "description": work.description,
        "language": edition.language,
        "publication_year": work.publication_year,
    }
    return {
        name: values[name]
        for name in METADATA_FIELDS
        if work.metadata_provenance.get(name) == PROVENANCE_USER
    }


def _configuration() -> tuple[ModelConfiguration, PromptTemplate]:
    model = settings.OPENAI_METADATA_MODEL
    configuration, _ = ModelConfiguration.objects.get_or_create(
        name="openai-metadata-v1",
        defaults={
            "provider": "openai",
            "model": model,
            "purpose": "import_metadata",
            "parameters": {
                "reasoning_effort": "low",
                "pricing_per_million": METADATA_MODEL_PRICING,
            },
        },
    )
    if configuration.model != model:
        configuration.model = model
        configuration.save(update_fields=["model", "updated_at"])
    prompt, _ = PromptTemplate.objects.get_or_create(
        name=PROMPT_NAME,
        version=PROMPT_VERSION,
        defaults={
            "purpose": "import_metadata",
            "system_prompt": METADATA_SYSTEM_PROMPT,
            "user_template": METADATA_USER_TEMPLATE,
            "output_schema": METADATA_OUTPUT_SCHEMA,
            "active": True,
        },
    )
    return configuration, prompt


def opening_excerpt(edition: Edition) -> str:
    """The first headings and paragraphs, capped so the call stays negligible."""

    blocks = (
        edition.blocks.exclude(text="")
        .filter(block_type__in=[ContentBlock.BlockType.HEADING, ContentBlock.BlockType.PARAGRAPH])
        .order_by("chapter__sequence", "sequence")
        .values_list("text", flat=True)[:METADATA_EXCERPT_MAX_BLOCKS]
    )
    excerpt = "\n\n".join(blocks)
    return excerpt[:METADATA_EXCERPT_MAX_CHARS]


def _propose_with_ai(edition: Edition, run: PipelineRun) -> AIRun | None:
    excerpt = opening_excerpt(edition)
    if not excerpt:
        return None
    configuration, prompt_template = _configuration()
    declared = {
        "title": edition.title or "(none)",
        "author": edition.author or "(none)",
        "language": edition.language or "(none)",
    }
    system_prompt = prompt_template.system_prompt.format(
        supported_languages=", ".join(language.code for language in LANGUAGES)
    )
    user_prompt = prompt_template.user_template.format(
        declared_title=declared["title"],
        declared_author=declared["author"],
        declared_language=declared["language"],
        excerpt_chars=len(excerpt),
        excerpt=excerpt,
    )
    # The stage hash already covers the source and the owner's input; a retry
    # after a crash finds the finished call instead of paying for it again.
    ai_run, created = AIRun.objects.get_or_create(
        idempotency_key=f"{edition.id}:{run.input_hash}:openai-metadata:v{PROMPT_VERSION}",
        defaults={
            "edition": edition,
            "pipeline_run": run,
            "model_configuration": configuration,
            "prompt_template": prompt_template,
            "input_hash": run.input_hash,
        },
    )
    if not created and ai_run.status == AIRun.Status.SUCCEEDED:
        return ai_run

    ai_run.status = AIRun.Status.SUBMITTED
    ai_run.provider_request_id = f"direct:{ai_run.id}"
    ai_run.started_at = timezone.now()
    ai_run.error = ""
    ai_run.request_payload = {
        "execution": "direct",
        "declared": declared,
        "excerpt_chars": len(excerpt),
    }
    ai_run.save(
        update_fields=[
            "status",
            "provider_request_id",
            "started_at",
            "error",
            "request_payload",
            "updated_at",
        ]
    )

    body = {
        "model": configuration.model,
        "instructions": system_prompt,
        "input": user_prompt,
        "reasoning": {"effort": "low"},
        "text": {
            "format": {
                "type": "json_schema",
                "name": "book_metadata",
                "strict": True,
                "schema": METADATA_OUTPUT_SCHEMA,
            }
        },
        "store": False,
    }
    try:
        response = OpenAIBatchProvider().respond(body)
        proposal = BookMetadataProposal.model_validate_json(response_output_text(response))
    except Exception as error:
        ai_run.status = AIRun.Status.FAILED
        ai_run.error = str(error)[:10000]
        ai_run.finished_at = timezone.now()
        ai_run.save(update_fields=["status", "error", "finished_at", "updated_at"])
        return ai_run

    usage = response.get("usage") or {}
    ai_run.input_tokens = usage.get("input_tokens", 0)
    ai_run.cached_input_tokens = (usage.get("input_tokens_details") or {}).get("cached_tokens", 0)
    ai_run.output_tokens = usage.get("output_tokens", 0)
    ai_run.reasoning_tokens = (usage.get("output_tokens_details") or {}).get("reasoning_tokens", 0)
    ai_run.estimated_cost_usd = _estimated_cost(
        ai_run.input_tokens, ai_run.cached_input_tokens, ai_run.output_tokens
    )
    ai_run.status = AIRun.Status.SUCCEEDED
    ai_run.finished_at = timezone.now()
    ai_run.response_payload = {"proposal": proposal.model_dump(mode="json")}
    ai_run.save(
        update_fields=[
            "status",
            "input_tokens",
            "cached_input_tokens",
            "output_tokens",
            "reasoning_tokens",
            "estimated_cost_usd",
            "response_payload",
            "finished_at",
            "updated_at",
        ]
    )
    return ai_run


def _estimated_cost(input_tokens: int, cached_input_tokens: int, output_tokens: int) -> Decimal:
    uncached = max(0, input_tokens - cached_input_tokens)
    return (
        Decimal(uncached) * Decimal(METADATA_MODEL_PRICING["input"])
        + Decimal(cached_input_tokens) * Decimal(METADATA_MODEL_PRICING["cached_input"])
        + Decimal(output_tokens) * Decimal(METADATA_MODEL_PRICING["output"])
    ) / Decimal(1_000_000)


def _supported_language(value: str) -> str:
    try:
        return normalize_language_code(value) if value.strip() else ""
    except ValueError:
        return ""


def _apply_proposal(
    edition: Edition, proposal: BookMetadataProposal, provenance: dict[str, str]
) -> None:
    """Adopt the proposal for every field the owner did not type at upload."""

    work = edition.work
    owns_work = _edition_owns_work(edition)

    def open_field(name: str) -> bool:
        return provenance.get(name) != PROVENANCE_USER

    title = proposal.title.strip()[:500]
    if open_field("title") and title and title != edition.title:
        edition.title = title
        if owns_work:
            work.title = title
            provenance["title"] = PROVENANCE_AI
    author = proposal.author.strip()[:300]
    if open_field("author") and author and author != edition.author:
        edition.author = author
        if owns_work:
            work.author = author
            provenance["author"] = PROVENANCE_AI
    language = _supported_language(proposal.language)
    if open_field("language") and language and language != edition.language:
        edition.language = language
        if owns_work:
            work.original_language = language
            provenance["language"] = PROVENANCE_AI
    description = proposal.description.strip()
    if open_field("description") and description:
        work.description = description
        provenance["description"] = PROVENANCE_AI
    year = proposal.publication_year
    if open_field("publication_year") and year is not None and 1 <= year <= 9999:
        work.publication_year = year
        provenance["publication_year"] = PROVENANCE_AI


def metadata_payload(edition: Edition) -> dict[str, Any]:
    """The metadata block shared by the internal API and the import event."""

    work = edition.work
    return {
        "title": edition.title,
        "author": edition.author,
        "description": work.description,
        "language": edition.language or None,
        "publication_year": work.publication_year,
        "provenance": work.metadata_provenance,
        "detected": work.metadata_detected_at is not None,
    }
