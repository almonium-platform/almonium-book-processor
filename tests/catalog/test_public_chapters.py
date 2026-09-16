from unittest.mock import patch

import pytest

from almonium_book_processor.catalog.chapter_analysis import current_chapter_hashes
from almonium_book_processor.catalog.chapter_projections import DIFFICULTY_VERSION, SUMMARY_VERSION
from almonium_book_processor.catalog.models import (
    Chapter,
    ContentBlock,
    Edition,
    EditionArtifact,
    Work,
)


@pytest.mark.django_db
def test_public_chapters_are_safe_current_projections(client):
    work = Work.objects.create(slug="chapters", title="Book", author="Author")
    edition = Edition.objects.create(
        work=work, slug="chapters-en", language="en", status="published"
    )
    chapter = Chapter.objects.create(edition=edition, sequence=10, title="IV")
    url = "/api/v1/public/editions/chapters-en/chapters/"
    assert client.get(url).json()[0]["cefrEstimate"] is None
    context = {
        "projection_state": "complete",
        "chapter_projections": [
            {
                "chapter": chapter,
                "difficulty": {"complete": True, "cefr_estimate": "B2", "evidence": "secret"},
                "summary": {
                    "complete": True,
                    "sections": [
                        {"spoiler_free_description": "A difficult choice.", "recap": "The ending."}
                    ],
                },
            }
        ],
    }
    with patch(
        "almonium_book_processor.catalog.public_chapters.analysis_context", return_value=context
    ):
        assert client.get(url).json() == [
            {
                "id": str(chapter.id),
                "sequence": 10,
                "title": "IV",
                "analysisStatus": "complete",
                "cefrEstimate": "B2",
                "descriptions": ["A difficult choice."],
            }
        ]
        context["chapter_projections"][0]["difficulty"]["complete"] = False
        context["chapter_projections"][0]["summary"]["complete"] = False
        context["projection_state"] = "partial"
        assert client.get(url).json()[0]["cefrEstimate"] is None
        assert client.get(url).json()[0]["descriptions"] == []
    edition.status = Edition.Status.REVIEW
    edition.save()
    assert client.get(url).status_code == 404
    edition.status = Edition.Status.PUBLISHED
    edition.save()
    work.visibility = Work.Visibility.PRIVATE
    work.save()
    assert client.get(url).status_code == 404


@pytest.mark.django_db
def test_public_chapters_keep_the_last_complete_projection_when_the_run_is_stale(client):
    work = Work.objects.create(slug="kept", title="Book", author="Author")
    edition = Edition.objects.create(
        work=work, slug="kept-en", language="en", status="published", source_sha256="a" * 64
    )
    chapters = [
        Chapter.objects.create(edition=edition, sequence=n, title=f"Chapter {n}") for n in (1, 2, 3)
    ]
    for chapter in chapters:
        ContentBlock.objects.create(
            edition=edition,
            chapter=chapter,
            block_id=f"c{chapter.sequence}.p1",
            sequence=1,
            block_type=ContentBlock.BlockType.PARAGRAPH,
            text=f"W e were brought up together in chapter {chapter.sequence}.",
        )
    hashes = current_chapter_hashes(edition)
    counter = iter(range(100))

    def persist(chapter, cefr, description):
        common = {
            "complete": True,
            "chapter_hash": hashes[str(chapter.id)],
            "analysis_spec_hash": "spec",
        }
        for kind, version, extra in (
            (
                EditionArtifact.Kind.DIFFICULTY,
                DIFFICULTY_VERSION,
                {"cefr_estimate": cefr, "evidence": "secret"},
            ),
            (
                EditionArtifact.Kind.CHAPTER_SUMMARY,
                SUMMARY_VERSION,
                {"sections": [{"spoiler_free_description": description, "recap": "The ending."}]},
            ),
        ):
            EditionArtifact.objects.create(
                edition=edition,
                chapter=chapter,
                kind=kind,
                input_hash=f"{next(counter):064d}",
                processor_version=version,
                payload={**common, **extra},
                is_current=False,
            )

    persist(chapters[0], "B2", "An older description.")
    persist(chapters[0], "C1", "The newest description.")
    persist(chapters[1], "B1", "An unchanged chapter.")
    # A drop-cap repair on chapter 1 makes the run stale; chapter 2 is untouched
    # and chapter 3 was never analyzed.
    ContentBlock.objects.filter(chapter=chapters[0]).update(
        text="We were brought up together in chapter 1."
    )
    url = "/api/v1/public/editions/kept-en/chapters/"
    context = {"projection_state": "stale", "chapter_projections": []}
    with patch(
        "almonium_book_processor.catalog.public_chapters.analysis_context", return_value=context
    ):
        response = client.get(url)
        rows = response.json()
        assert [(r["analysisStatus"], r["cefrEstimate"], r["descriptions"]) for r in rows] == [
            ("stale", "C1", ["The newest description."]),
            ("complete", "B1", ["An unchanged chapter."]),
            ("stale", None, []),
        ]
        assert "secret" not in response.content.decode()
        assert "ending" not in response.content.decode()
        # While a new run is still working, chapters it has not reached keep them too.
        context["projection_state"] = "running"
        context["chapter_projections"] = [
            {
                "chapter": chapters[1],
                "difficulty": {"complete": False},
                "summary": {"complete": False},
            }
        ]
        rows = client.get(url).json()
        assert rows[1]["descriptions"] == ["An unchanged chapter."]
        assert rows[2]["analysisStatus"] == "running"
