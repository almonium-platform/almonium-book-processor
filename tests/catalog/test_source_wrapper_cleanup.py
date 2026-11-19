from io import BytesIO
from zipfile import ZipFile

import pytest
from django.core.files.base import ContentFile

from almonium_book_processor.catalog.models import Chapter, ContentBlock, EditionArtifact
from almonium_book_processor.catalog.source_wrapper_cleanup import (
    apply_source_wrappers,
    plan_source_wrappers,
)
from tests.catalog.test_sentence_alignment import pair  # noqa: F401

pytestmark = pytest.mark.django_db


def test_repairs_source_tagged_chapters_and_preserves_historical_artifacts(
    pair,  # noqa: F811
    settings,
    tmp_path,
):
    edition, _ = pair
    settings.MEDIA_ROOT = tmp_path
    doc = "chapter.xhtml"
    source = BytesIO()
    notice = "This e-text was produced from Project Runeberg’s digital facsimile edition of a book."
    with ZipFile(source, "w") as archive:
        archive.writestr(
            doc,
            f'<p>{notice}</p><p><span class="pageNum">79</span></p><p>More prose.</p>'
            '<p><span class="pageNum">80</span></p><h2>80</h2>',
        )
    edition.source_file.save("source.epub", ContentFile(source.getvalue()))
    opening = edition.chapters.get()
    false = Chapter.objects.create(edition=edition, sequence=12, title="79")
    next_chapter = Chapter.objects.create(edition=edition, sequence=13, title="80")
    heading = ContentBlock.objects.create(
        edition=edition,
        chapter=false,
        sequence=1,
        block_type="heading",
        block_id="c12.h1",
        text="79",
        source_ref=doc,
    )
    prose = ContentBlock.objects.create(
        edition=edition,
        chapter=false,
        sequence=2,
        block_type="paragraph",
        block_id="c12.p2",
        text="More prose.",
        source_ref=doc,
    )
    ContentBlock.objects.create(
        edition=edition,
        chapter=next_chapter,
        sequence=1,
        block_type="heading",
        block_id="c13.h1",
        text="80",
        source_ref=doc,
    )
    ContentBlock.objects.create(
        edition=edition,
        chapter=opening,
        sequence=2,
        block_type="paragraph",
        block_id="c11.p2",
        text=notice,
        source_ref=doc,
    )
    judgment = EditionArtifact.objects.create(
        edition=edition,
        chapter=false,
        kind="difficulty",
        processor_version="test",
        input_hash="test",
        payload={"saved": "paid reading"},
    )
    targets, counts = plan_source_wrappers()
    assert counts["false page heading"] == 1
    assert counts["digital wrapper"] == 1
    assert apply_source_wrappers(targets)["false chapters merged"] == 1

    prose.refresh_from_db()
    assert (prose.chapter_id, prose.sequence, prose.text) == (opening.pk, 2, "More prose.")
    assert list(edition.chapters.order_by("sequence").values_list("pk", "sequence")) == [
        (opening.pk, 11),
        (next_chapter.pk, 12),
    ]
    judgment.refresh_from_db()
    assert judgment.chapter_id == opening.pk
    assert not judgment.is_current and judgment.payload == {"saved": "paid reading"}
    saved = edition.pipeline_runs.get(summary__has_key="source_wrapper_archive").summary
    assert {row["text"] for row in saved["source_wrapper_archive"]["blocks"]} == {
        heading.text,
        notice,
    }
    assert not plan_source_wrappers()[0]
