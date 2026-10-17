"""Chapter roles are read off the titles at ingest; nobody tags front matter by hand."""

from __future__ import annotations

import uuid

import pytest

from almonium_book_processor.catalog.front_matter import chapter_roles, retag
from almonium_book_processor.catalog.models import Chapter, Edition, PipelineRun, Work
from almonium_book_processor.catalog.services import persist_artifact
from almonium_book_processor.models import (
    BlockType,
    BookArtifact,
    EditionMetadata,
    SourceMetadata,
)
from almonium_book_processor.models import (
    ContentBlock as ArtifactBlock,
)

pytestmark = pytest.mark.django_db


def test_untitled_leading_chapters_and_a_preface_are_front_matter():
    # Alice: a title page and the dedication poem before Chapter I
    assert chapter_roles(["", "", "CHAPTER I. Down the Rabbit-Hole", "CHAPTER II."]) == [
        "front",
        "front",
        "body",
        "body",
    ]
    # Bleak House: the preface too
    assert chapter_roles(["", "", "PREFACE.", "CHAPTER I. IN CHANCERY.", "CHAPTER II."]) == [
        "front",
        "front",
        "front",
        "body",
        "body",
    ]
    # Frankenstein: Shelley's introduction and preface, then the letters
    assert chapter_roles(["INTRODUCTION.", "PREFACE.", "LETTER I.", "CHAPTER I."]) == [
        "front",
        "front",
        "body",
        "body",
    ]


def test_a_numbered_chapter_is_the_story_whatever_it_is_called():
    # The Time Machine: Wells calls his first chapter "Introduction"; the epilogue is the
    # story's, the notes after it are back matter
    titles = ["", "", "", "I INTRODUCTION", "II", "XV", "Epilogue", "NOTES"]
    assert chapter_roles(titles) == ["front"] * 3 + ["body"] * 4 + ["back"]


def test_titled_publisher_pages_before_the_first_numbered_chapter_are_front_matter():
    # Candide from Gutenberg: two title pages and the editor's preface, then CHAPITRE I
    titles = ["OEUVRES", "Préface de l’Éditeur", "CANDIDE,", "CHAPITRE I. Comment Candide fut"]
    assert chapter_roles(titles) == ["front", "front", "front", "body"]
    # a book whose chapters are titled, never numbered, keeps every titled chapter
    assert chapter_roles(["LE CRIME AU PÈRE BONIFACE", "ROSE", "LE PÈRE"]) == ["body"] * 3


def test_a_book_of_bare_numerals_or_without_titles_is_all_story():
    assert chapter_roles(["I", "II", "III"]) == ["body"] * 3
    assert chapter_roles(["", "", ""]) == ["body"] * 3
    # an untitled chapter inside the story is the story's
    assert chapter_roles(["CHAPTER I.", "", "CHAPTER III."]) == ["body"] * 3


def _edition(slug="roles"):
    work = Work.objects.create(slug=f"{slug}-work", title="Book", author="Ada")
    return Edition.objects.create(
        slug=slug,
        work=work,
        title="Book",
        author="Ada",
        language="en",
        edition_type="original",
        status=Edition.Status.PROCESSING,
    )


def _artifact(edition, chapters):
    blocks = []
    for number, heading in chapters:
        if heading:
            blocks.append(
                ArtifactBlock(
                    edition_slug=edition.slug,
                    block_id=f"c{number}.h1",
                    chapter=number,
                    seq=1,
                    type=BlockType.HEADING,
                    text=heading,
                )
            )
        blocks.append(
            ArtifactBlock(
                edition_slug=edition.slug,
                block_id=f"c{number}.p1",
                chapter=number,
                seq=2 if heading else 1,
                type=BlockType.PARAGRAPH,
                text=f"Text of chapter {number}.",
            )
        )
    return BookArtifact(
        processor_version="test",
        edition=EditionMetadata(
            edition_slug=edition.slug,
            work_slug=edition.work.slug,
            title=edition.title,
            author=edition.author,
            language=edition.language,
            source=SourceMetadata(format="tei", path="book.xml", sha256="a" * 64),
        ),
        blocks=blocks,
    )


def test_ingest_tags_the_chapters_from_their_titles():
    edition = _edition()
    run = PipelineRun.objects.create(
        edition=edition,
        stage=PipelineRun.Stage.INGEST,
        processor_version="test",
        input_hash="a" * 64,
        idempotency_key=f"{edition.slug}-{uuid.uuid4()}",
    )
    chapters = [(0, ""), (1, "PREFACE."), (2, "CHAPTER I."), (3, "NOTES")]
    persist_artifact(edition, _artifact(edition, chapters), run)

    roles = list(edition.chapters.order_by("sequence").values_list("analysis_role", flat=True))
    assert roles == ["front", "front", "body", "back"]


def test_retagging_reads_an_original_and_copies_a_source_to_its_editions():
    source = _edition("source")
    for sequence, title in enumerate(["", "CHAPTER I.", "CHAPTER II."]):
        Chapter.objects.create(edition=source, sequence=sequence, title=title)
    adaptation = Edition.objects.create(
        slug="source-b1",
        work=source.work,
        title="Book",
        author="Ada",
        language="en",
        edition_type="adaptation",
        source_edition=source,
        status=Edition.Status.READY,
    )
    for sequence in range(3):
        Chapter.objects.create(edition=adaptation, sequence=sequence, title="")

    assert retag(source) == 1
    assert retag(adaptation) == 1
    assert retag(adaptation) == 0
    assert adaptation.chapters.get(sequence=0).analysis_role == "front"
    assert adaptation.chapters.get(sequence=2).analysis_role == "body"
