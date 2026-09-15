from unittest.mock import patch

import pytest

from almonium_book_processor.catalog.models import Chapter, Edition, Work


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
