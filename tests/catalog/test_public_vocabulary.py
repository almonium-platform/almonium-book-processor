import pytest

from almonium_book_processor.catalog.models import (
    Chapter,
    ContentBlock,
    Edition,
    EditionArtifact,
    PipelineRun,
    Work,
)
from almonium_book_processor.catalog.public_vocabulary import lexical_input_hash
from almonium_book_processor.processing.lexical import (
    LEXICAL_PROCESSOR_VERSION,
    LEXICAL_SCHEMA_VERSION,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def vocabulary():
    work = Work.objects.create(slug="vocab", title="Book", author="Author")
    edition = Edition.objects.create(
        work=work, slug="vocab-en", language="en", status="published", source_sha256="a" * 64
    )
    chapter = Chapter.objects.create(edition=edition, sequence=11, title="V")
    block = ContentBlock.objects.create(
        edition=edition,
        chapter=chapter,
        sequence=1,
        block_id="c11.p1",
        block_type="paragraph",
        text="Two lanterns burned.",
    )
    runtime = {
        "spacy_model": "en_core_web_sm",
        "spacy_model_version": "3.8.0",
        "spacy_pipeline": ["tagger", "lemmatizer"],
    }
    digest = lexical_input_hash(edition, runtime)
    run = PipelineRun.objects.create(
        edition=edition,
        stage="lexical",
        status="succeeded",
        input_hash=digest,
        processor_version=LEXICAL_PROCESSOR_VERSION,
        idempotency_key="test-vocabulary",
        summary={"runtime": runtime},
    )
    artifact = EditionArtifact.objects.create(
        edition=edition,
        kind="useful_words",
        schema_version=LEXICAL_SCHEMA_VERSION,
        processor_version=LEXICAL_PROCESSOR_VERSION,
        input_hash=digest,
        pipeline_run=run,
        payload={
            "provenance": runtime,
            "words": [
                {
                    "lemma": "lantern",
                    "frequency_band": "uncommon",
                    "chapter_occurrences": [
                        {
                            "chapter": 11,
                            "block_id": "c11.p1",
                            "surface": "lanterns",
                            "start": 4,
                            "end": 12,
                            "lemma_source": "spacy_model",
                        }
                    ],
                }
            ],
        },
    )
    return edition, chapter, block, artifact


URL = "/api/v1/public/editions/vocab-en/chapters/11/vocabulary/"


def test_public_vocabulary_is_attested_chapter_local_and_reader_safe(
    client, vocabulary, monkeypatch
):
    def forbidden(*args, **kwargs):
        raise AssertionError("HTTP must not run NLP")

    monkeypatch.setattr("almonium_book_processor.processing.lexical._lexical_pipeline", forbidden)
    response = client.get(URL)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ready"
    assert data["words"] == [
        {
            "lemma": "lantern",
            "surface": "lanterns",
            "context": "Two lanterns burned.",
            "blockId": "c11.p1",
            "start": 4,
            "end": 12,
            "frequencyBand": "uncommon",
        }
    ]
    assert data["provenance"]["spacyModel"] == "en_core_web_sm"
    edition, _, _, _ = vocabulary
    Chapter.objects.create(edition=edition, sequence=12)
    assert client.get(URL.replace("/11/", "/12/")).json()["words"] == []
    assert client.get(URL.replace("/11/", "/99/")).status_code == 404


@pytest.mark.parametrize("mutation", ["text", "source", "version", "current", "failed", "runtime"])
def test_stale_or_unverified_artifacts_never_leak_words(client, vocabulary, mutation):
    edition, chapter, block, artifact = vocabulary
    if mutation == "text":
        block.text = "No lanterns now."
        block.save()
    elif mutation == "source":
        edition.source_sha256 = "b" * 64
        edition.save()
    elif mutation == "version":
        artifact.processor_version = "lexical-v2"
        artifact.save()
    elif mutation == "current":
        artifact.is_current = False
        artifact.save()
    elif mutation == "failed":
        artifact.pipeline_run.status = "failed"
        artifact.pipeline_run.save()
    else:
        artifact.payload["provenance"]["spacy_pipeline"] = []
        artifact.save()
    assert client.get(URL).json()["words"] == []


@pytest.mark.parametrize("mutation", ["surface", "chapter", "fallback", "offset"])
def test_invalid_occurrence_is_not_a_vocabulary_entry(client, vocabulary, mutation):
    artifact = vocabulary[3]
    occurrence = artifact.payload["words"][0]["chapter_occurrences"][0]
    occurrence.update(
        {"surface": "invented"}
        if mutation == "surface"
        else {"chapter": 12}
        if mutation == "chapter"
        else {"lemma_source": "fallback"}
        if mutation == "fallback"
        else {"start": -1}
    )
    artifact.save()
    assert client.get(URL).json()["words"] == []


def test_private_and_unpublished_editions_are_not_exposed(client, vocabulary):
    edition = vocabulary[0]
    edition.status = "review"
    edition.save()
    assert client.get(URL).status_code == 404
    edition.status = "published"
    edition.save()
    edition.work.visibility = "private"
    edition.work.save()
    assert client.get(URL).status_code == 404
