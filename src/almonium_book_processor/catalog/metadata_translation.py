"""Name and describe a parallel translation in its own language.

A block-for-block translation is read beside its source. Its reading demand is
the source's, and no analysis rubric is ever applied to machine-translated
text; what the edition needs of its own is a title page (title, author, blurb)
and the chapter descriptions its readers see in the contents, translated from
the source's. One small direct run does both. Every call is keyed by what it
translates, so a retry or a repeat run costs nothing, and a chapter description
is served only while it still describes the source's current analysis.
"""

from __future__ import annotations

import json
import logging
import time

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from almonium_book_processor.ai.openai_provider import OpenAIBatchProvider, response_output_text
from almonium_book_processor.ai.output_language import validate_output_language
from almonium_book_processor.ai.translation import (
    CHAPTER_SUMMARY_OUTPUT_SCHEMA,
    CHAPTER_SUMMARY_SYSTEM_PROMPT,
    CHAPTER_SUMMARY_USER_TEMPLATE,
    TITLE_PAGE_OUTPUT_SCHEMA,
    TITLE_PAGE_SYSTEM_PROMPT,
    TITLE_PAGE_USER_TEMPLATE,
    ChapterSummaryTranslation,
    TitlePageTranslation,
)
from almonium_book_processor.catalog.adaptation import digest, record_response
from almonium_book_processor.catalog.ai_translation import (
    _configuration,
    _response_request,
    language_name,
)
from almonium_book_processor.catalog.models import (
    AIRun,
    Edition,
    EditionArtifact,
    PipelineRun,
    PromptTemplate,
    QAWarning,
)

logger = logging.getLogger(__name__)

VERSION = "metadata-translation-v1"
TITLE_PAGE_PROMPT = ("literary-title-page", 2)
CHAPTER_SUMMARY_PROMPT = ("literary-chapter-summary", 1)
TITLE_PAGE_WARNING = "translation_title_page"
KIND = EditionArtifact.Kind.CHAPTER_SUMMARY_TRANSLATION


def _template(name: str, version: int, system_prompt: str, user_template: str, schema: dict):
    template, _ = PromptTemplate.objects.get_or_create(
        name=name,
        version=version,
        defaults={
            "purpose": "literary_translation",
            "system_prompt": system_prompt,
            "user_template": user_template,
            "output_schema": schema,
            "active": True,
        },
    )
    return template


def _templates() -> tuple[PromptTemplate, PromptTemplate]:
    return (
        _template(
            *TITLE_PAGE_PROMPT,
            TITLE_PAGE_SYSTEM_PROMPT,
            TITLE_PAGE_USER_TEMPLATE,
            TITLE_PAGE_OUTPUT_SCHEMA,
        ),
        _template(
            *CHAPTER_SUMMARY_PROMPT,
            CHAPTER_SUMMARY_SYSTEM_PROMPT,
            CHAPTER_SUMMARY_USER_TEMPLATE,
            CHAPTER_SUMMARY_OUTPUT_SCHEMA,
        ),
    )


def _spec(edition: Edition) -> dict:
    configuration, _ = _configuration("quality")
    return {
        "processor": VERSION,
        "model": configuration.model,
        "title_page_prompt": f"{TITLE_PAGE_PROMPT[0]} v{TITLE_PAGE_PROMPT[1]}",
        "chapter_summary_prompt": f"{CHAPTER_SUMMARY_PROMPT[0]} v{CHAPTER_SUMMARY_PROMPT[1]}",
        "target_language": edition.language,
    }


def title_page_inputs(edition: Edition) -> dict:
    source = edition.source_edition
    return {
        "title": source.title,
        "author": source.author,
        "description": source.public_description,
    }


def title_page_hash(edition: Edition) -> str:
    """What the title page was translated from; a change means it must be again."""

    return digest([title_page_inputs(edition), _spec(edition)])


def chapter_inputs(edition: Edition) -> list[dict]:
    """The source's current chapter descriptions, matched to this edition's chapters.

    A generated translation mirrors the source chapter by chapter, so the
    sequence pairs them. Each entry carries the hashes the source's summary is
    keyed by: a translated description is only ever served for the exact
    analysis it was made from.
    """

    from almonium_book_processor.catalog.public_chapters import chapter_rows

    own = {chapter.sequence: chapter for chapter in edition.chapters.all()}
    inputs = []
    for row in chapter_rows(edition.source_edition):
        chapter = own.get(row["sequence"])
        if chapter is None or not row["descriptions"]:
            continue
        inputs.append(
            {
                "chapter_id": str(chapter.id),
                "source_chapter_id": row["id"],
                "sequence": row["sequence"],
                "title": chapter.title or row["title"],
                "chapter_hash": row["chapter_hash"],
                "analysis_spec_hash": row["analysis_spec_hash"],
                "descriptions": row["descriptions"],
            }
        )
    return inputs


def _chapter_key(edition: Edition, item: dict, spec: dict) -> str:
    return digest(
        [
            item["chapter_hash"],
            item["analysis_spec_hash"],
            item["descriptions"],
            spec["model"],
            spec["chapter_summary_prompt"],
            edition.language,
        ]
    )


def translated_summaries(edition: Edition) -> dict[str, dict]:
    """Current translated descriptions keyed by the source chapter id."""

    return {
        artifact.payload["source_chapter_id"]: artifact.payload
        for artifact in edition.artifacts.filter(
            kind=KIND, is_current=True, processor_version=VERSION
        ).order_by("created_at")
    }


def title_page_current(edition: Edition) -> bool:
    """Whether the edition's name and blurb come from its source's current ones."""

    return edition.pipeline_runs.filter(
        stage=PipelineRun.Stage.TRANSLATE_METADATA,
        status=PipelineRun.Status.SUCCEEDED,
        summary__title_page_hash=title_page_hash(edition),
    ).exists()


def _plan(edition: Edition) -> dict:
    return {
        "spec": _spec(edition),
        "title_page": title_page_inputs(edition),
        "title_page_hash": title_page_hash(edition),
        "chapters": chapter_inputs(edition),
    }


@transaction.atomic
def queue_metadata_translation(edition_id: str, *, dispatch: bool = True) -> PipelineRun:
    from almonium_book_processor.catalog.tasks import translate_edition_metadata

    # Lock only this row: source_edition is nullable, and PostgreSQL refuses
    # FOR UPDATE across the outer join a joined fetch would make.
    edition = Edition.objects.select_for_update(of=("self",)).get(pk=edition_id)
    if not edition.is_parallel_translation:
        raise ValueError("Only a parallel translation is named and described from its source.")
    if not settings.OPENAI_API_KEY:
        raise ValueError("Configure an OpenAI key to translate metadata.")
    plan = _plan(edition)
    input_hash = digest(plan)
    run, _ = PipelineRun.objects.get_or_create(
        idempotency_key=f"{edition.id}:translate-metadata:{input_hash}",
        defaults={
            "edition": edition,
            "stage": PipelineRun.Stage.TRANSLATE_METADATA,
            "processor_version": VERSION,
            "input_hash": input_hash,
            "summary": {
                "title_page_hash": plan["title_page_hash"],
                "chapters_available": len(plan["chapters"]),
            },
        },
    )
    if run.status in {PipelineRun.Status.SUCCEEDED, PipelineRun.Status.RUNNING}:
        return run
    run.status = PipelineRun.Status.QUEUED
    run.error = ""
    run.finished_at = None
    run.save(update_fields=["status", "error", "finished_at", "updated_at"])
    if dispatch:
        transaction.on_commit(lambda: translate_edition_metadata.delay(str(run.id)))
    return run


def queue_for_translations_of(source: Edition) -> list[PipelineRun]:
    """Queue the run for every parallel translation of ``source`` that has text.

    Called when the source's chapter analysis completes: its descriptions
    changed, so each companion's contents need translating again. Only the
    chapters whose descriptions changed are paid for.
    """

    runs = []
    for edition in source.derived_editions.select_related("source_edition", "work").filter(
        parallel_role=Edition.ParallelRole.PARALLEL,
        status__in=[Edition.Status.REVIEW, Edition.Status.READY, Edition.Status.PUBLISHED],
    ):
        if not edition.is_parallel_translation:
            continue
        try:
            runs.append(queue_metadata_translation(str(edition.id)))
        except ValueError:
            logger.info("Metadata translation not queued for %s", edition.slug, exc_info=True)
    return runs


# The provider has answered a bare, empty 404 to a request it completes a
# moment later. Its own client retries 408/409/429 and 5xx; these are ours.
TRANSIENT_STATUSES = {404, 408, 409, 429, 500, 502, 503, 504}
RETRY_DELAYS = (2, 8)


def _respond(provider, body: dict) -> dict:
    for attempt, delay in enumerate((*RETRY_DELAYS, None)):
        try:
            return provider.respond(body)
        except Exception as error:
            status = getattr(error, "status_code", None)
            if delay is None or status not in TRANSIENT_STATUSES:
                raise
            logger.warning("Provider answered HTTP %s; retry %d", status, attempt + 1)
            time.sleep(delay)
    raise AssertionError("unreachable")


def _call(edition, run, key, configuration, template, body, model_class, provider):
    """One checkpointed direct call: a finished result is reused, never paid for again."""

    ai_run, created = AIRun.objects.get_or_create(
        idempotency_key=key,
        defaults={
            "edition": edition,
            "pipeline_run": run,
            "model_configuration": configuration,
            "prompt_template": template,
            "input_hash": digest(body),
            "request_payload": {"execution": "direct", "body": body},
        },
    )
    if not created and ai_run.status == AIRun.Status.SUCCEEDED:
        result = model_class.model_validate(ai_run.response_payload["result"])
        validate_output_language(
            result.descriptions
            if isinstance(result, ChapterSummaryTranslation)
            else [result.description],
            edition.language,
        )
        return ai_run, result
    ai_run.status = AIRun.Status.SUBMITTED
    ai_run.pipeline_run = run
    ai_run.started_at = timezone.now()
    ai_run.error = ""
    ai_run.save(update_fields=["status", "pipeline_run", "started_at", "error", "updated_at"])
    try:
        response = _respond(provider, body)
        record_response(ai_run.id, response)
        if response.get("status") != "completed":
            raise ValueError("Provider did not complete the request.")
        result = model_class.model_validate_json(response_output_text(response))
        validate_output_language(
            result.descriptions
            if isinstance(result, ChapterSummaryTranslation)
            else [result.description],
            edition.language,
        )
    except Exception as error:
        AIRun.objects.filter(pk=ai_run.id).update(
            status=AIRun.Status.FAILED,
            error=_describe(error)[:2000],
            finished_at=timezone.now(),
            updated_at=timezone.now(),
        )
        raise
    ai_run.refresh_from_db()
    AIRun.objects.filter(pk=ai_run.id).update(
        status=AIRun.Status.SUCCEEDED,
        response_payload={**ai_run.response_payload, "result": result.model_dump()},
        finished_at=timezone.now(),
        updated_at=timezone.now(),
    )
    return ai_run, result


def _title_page(edition, run, plan, configuration, template, provider):
    naming = _naming(edition)
    inputs = plan["title_page"]
    body = _response_request(
        configuration.model,
        template.system_prompt.format(**naming),
        template.user_template.format(
            title=inputs["title"],
            author=inputs["author"],
            description=inputs["description"] or "(none)",
            source_language=edition.source_edition.language,
            target_language=edition.language,
        ),
        "title-page",
        schema_name="title_page",
        schema=template.output_schema,
    )["body"]
    key = f"{edition.id}:{plan['title_page_hash']}:title-page"
    return _call(edition, run, key, configuration, template, body, TitlePageTranslation, provider)


def _chapter(edition, run, item, spec, configuration, template, provider):
    naming = _naming(edition)
    body = _response_request(
        configuration.model,
        template.system_prompt.format(**naming),
        template.user_template.format(
            chapter_sequence=item["sequence"],
            chapter_title_clause=f" · {item['title']}" if item["title"] else "",
            source_language=edition.source_edition.language,
            target_language=edition.language,
            descriptions=json.dumps(item["descriptions"], ensure_ascii=False, indent=1),
        ),
        f"chapter-{item['sequence']}",
        schema_name="chapter_summary",
        schema=template.output_schema,
    )["body"]
    key = f"{edition.id}:{_chapter_key(edition, item, spec)}:chapter-summary"
    ai_run, result = _call(
        edition, run, key, configuration, template, body, ChapterSummaryTranslation, provider
    )
    if len(result.descriptions) != len(item["descriptions"]) or not all(
        text.strip() for text in result.descriptions
    ):
        AIRun.objects.filter(pk=ai_run.id).update(
            status=AIRun.Status.FAILED, error="Description count changed", updated_at=timezone.now()
        )
        raise ValueError(f"Chapter {item['sequence']}: the description count changed.")
    payload = {
        "complete": True,
        "source_chapter_id": item["source_chapter_id"],
        "chapter_hash": item["chapter_hash"],
        "analysis_spec_hash": item["analysis_spec_hash"],
        "language": edition.language,
        "source_descriptions_hash": digest(item["descriptions"]),
        "descriptions": [text.strip() for text in result.descriptions],
        "ai_run_id": str(ai_run.id),
    }
    artifact, _ = EditionArtifact.objects.get_or_create(
        edition=edition,
        kind=KIND,
        input_hash=digest([item["chapter_id"], payload]),
        processor_version=VERSION,
        defaults={
            "chapter_id": item["chapter_id"],
            "pipeline_run": run,
            "payload": payload,
            # Served only once the whole run lands, together with the title page.
            "is_current": False,
        },
    )
    return artifact


def _naming(edition: Edition) -> dict:
    source = edition.source_edition
    year = source.work.publication_year
    return {
        "source_language_name": language_name(source.language),
        "target_language_name": language_name(edition.language),
        "work_title": source.work.title,
        "author": source.author,
        "year_clause": f", published {year}" if year else "",
    }


def _describe(error: Exception) -> str:
    """What went wrong, in words a retry decision can be made from, never book text."""

    if isinstance(error, ValueError):
        return str(error)[:1000]
    response = getattr(error, "response", None)
    if response is not None and getattr(response, "status_code", None):
        detail = getattr(response, "text", "") or ""
        return f"Provider answered HTTP {response.status_code}: {detail[:300]}".strip()
    return f"{type(error).__name__}: {str(error)[:300]}".strip(": ")


def run_metadata_translation(run_id: str, *, provider=None) -> None:
    if not PipelineRun.objects.filter(pk=run_id, status=PipelineRun.Status.QUEUED).update(
        status=PipelineRun.Status.RUNNING, started_at=timezone.now(), progress=1
    ):
        return
    run = PipelineRun.objects.select_related("edition__source_edition__work", "edition__work").get(
        pk=run_id
    )
    edition = run.edition
    provider = provider or OpenAIBatchProvider()
    try:
        plan = _plan(edition)
        if digest(plan) != run.input_hash:
            raise ValueError("The source changed; a new run was queued for it.")
        configuration, _ = _configuration("quality")
        title_template, summary_template = _templates()
        _, title_page = _title_page(edition, run, plan, configuration, title_template, provider)
        artifacts = []
        for index, item in enumerate(plan["chapters"], start=1):
            artifacts.append(
                _chapter(
                    edition, run, item, plan["spec"], configuration, summary_template, provider
                )
            )
            PipelineRun.objects.filter(pk=run.id).update(
                progress=int(100 * index / (len(plan["chapters"]) + 1))
            )
        with transaction.atomic():
            edition = Edition.objects.select_for_update().get(pk=edition.id)
            edition.title = title_page.title.strip()[:500]
            edition.author = title_page.author.strip()[:300]
            edition.description = title_page.description.strip()
            edition.save(update_fields=["title", "author", "description", "updated_at"])
            edition.warnings.filter(code=TITLE_PAGE_WARNING, resolved_at=None).delete()
            edition.artifacts.filter(kind=KIND, is_current=True).exclude(
                id__in=[artifact.id for artifact in artifacts]
            ).update(is_current=False)
            edition.artifacts.filter(id__in=[artifact.id for artifact in artifacts]).update(
                is_current=True
            )
            run.status = PipelineRun.Status.SUCCEEDED
            run.progress = 100
            run.finished_at = timezone.now()
            run.error = ""
            run.summary = {
                **run.summary,
                "title": edition.title,
                "author": edition.author,
                "note": title_page.note,
                "chapters": len(artifacts),
            }
            run.save(
                update_fields=[
                    "status",
                    "progress",
                    "finished_at",
                    "error",
                    "summary",
                    "updated_at",
                ]
            )
    except Exception as error:
        message = _describe(error)
        PipelineRun.objects.filter(pk=run.id).update(
            status=PipelineRun.Status.FAILED,
            error=message,
            finished_at=timezone.now(),
            updated_at=timezone.now(),
        )
        if not title_page_current(edition):
            QAWarning.objects.update_or_create(
                edition=edition,
                code=TITLE_PAGE_WARNING,
                source_ref="title-page",
                resolved_at=None,
                defaults={
                    "severity": QAWarning.Severity.WARNING,
                    "message": (
                        "The title, author and blurb are still in the source language: "
                        f"metadata translation failed ({message[:300]}). Run it again, or set "
                        "them in the metadata form."
                    ),
                },
            )
        raise
