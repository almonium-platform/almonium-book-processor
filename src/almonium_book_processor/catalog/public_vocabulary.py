"""Project existing lexical artifacts; never tokenize or call a provider on HTTP."""

import json

from django.conf import settings

from almonium_book_processor.catalog.models import EditionArtifact, PipelineRun
from almonium_book_processor.processing.lexical import (
    LEXICAL_PROCESSOR_VERSION,
    LEXICAL_SCHEMA_VERSION,
    TOKENIZER_LEMMA_LANGUAGES,
    _context,
)


def lexical_input_hash(edition, runtime):
    from almonium_book_processor.catalog.tasks import _text_hash

    return _text_hash(
        edition.source_sha256,
        list(
            edition.blocks.order_by("chapter__sequence", "sequence").values_list(
                "chapter__sequence", "block_id", "text"
            )
        ),
        edition.language,
        json.dumps(runtime, sort_keys=True),
        LEXICAL_PROCESSOR_VERSION,
    )


def public_vocabulary(edition, chapter):
    result = {
        "chapterId": str(chapter.id),
        "chapterSequence": chapter.sequence,
        "language": edition.language,
        "status": "pending",
        "selection": "book-useful-words-in-chapter",
        "words": [],
        "provenance": None,
    }
    candidates = edition.artifacts.filter(kind=EditionArtifact.Kind.USEFUL_WORDS)
    artifact = (
        candidates.filter(
            is_current=True,
            processor_version=LEXICAL_PROCESSOR_VERSION,
            schema_version=LEXICAL_SCHEMA_VERSION,
            pipeline_run__stage=PipelineRun.Stage.LEXICAL,
            pipeline_run__status=PipelineRun.Status.SUCCEEDED,
        )
        .select_related("pipeline_run")
        .first()
    )
    if artifact is None:
        result["status"] = "stale" if candidates.exists() else "pending"
        return result
    runtime = artifact.payload.get("provenance", {})
    model = runtime.get("spacy_model")
    pipes = runtime.get("spacy_pipeline", [])
    if (
        not model
        or model != settings.NLP_SPACY_MODELS.get(edition.language)
        or not runtime.get("spacy_model_version")
        or (
            not {"lemmatizer", "trainable_lemmatizer"}.intersection(pipes)
            and edition.language not in TOKENIZER_LEMMA_LANGUAGES
        )
    ):
        result["status"] = "unavailable"
        return result
    if (
        artifact.input_hash != lexical_input_hash(edition, runtime)
        or artifact.pipeline_run.input_hash != artifact.input_hash
        or artifact.pipeline_run.edition_id != edition.id
        or artifact.pipeline_run.summary.get("runtime") != runtime
    ):
        result["status"] = "stale"
        return result
    blocks = {b.block_id: b for b in chapter.blocks.all()}
    for word in artifact.payload.get("words", []):
        lemma = word.get("lemma")
        if not isinstance(lemma, str) or not lemma.strip():
            continue
        for occurrence in word.get("chapter_occurrences", []):
            if occurrence.get("chapter") != chapter.sequence:
                continue
            block = blocks.get(occurrence.get("block_id"))
            start, end = occurrence.get("start"), occurrence.get("end")
            surface = occurrence.get("surface")
            if (
                block is None
                or occurrence.get("lemma_source") != "spacy_model"
                or type(start) is not int
                or type(end) is not int
                or not 0 <= start < end <= len(block.text)
                or block.text[start:end] != surface
            ):
                continue
            result["words"].append(
                {
                    "lemma": lemma,
                    "surface": surface,
                    "context": _context(block.text, start, end),
                    "blockId": block.block_id,
                    "start": start,
                    "end": end,
                    "frequencyBand": word.get("frequency_band"),
                }
            )
            break
    result["status"] = "ready"
    result["provenance"] = {
        "inputHash": artifact.input_hash,
        "processorVersion": artifact.processor_version,
        "spacyModel": model,
        "spacyModelVersion": runtime["spacy_model_version"],
    }
    return result
