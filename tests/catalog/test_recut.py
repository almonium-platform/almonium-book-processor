"""A re-cut moves paragraphs into the chapters the current rules make; it rewrites nothing."""

from __future__ import annotations

import pytest
from django.core.files.base import ContentFile
from ebooklib import epub

from almonium_book_processor.catalog.models import Chapter, ContentBlock, Edition, PipelineRun, Work
from almonium_book_processor.catalog.recut import apply_recut, plan_recut
from almonium_book_processor.catalog.services import persist_artifact
from almonium_book_processor.ingest.epub import ingest_epub

pytestmark = pytest.mark.django_db


def _epub(tmp_path):
    source = tmp_path / "book.epub"
    book = epub.EpubBook()
    book.set_identifier("urn:test:recut")
    book.set_title("Pride and Prejudice")
    book.set_language("en")
    book.add_author("Jane Austen")
    items = []
    for number, name in enumerate(("Chapter I", "Chapter II", "Chapter III"), 1):
        item = epub.EpubHtml(title=name, file_name=f"text/c{number}.xhtml", lang="en")
        item.content = f"<h2>{name}</h2><p>First paragraph of {name}.</p><p>Second of {name}.</p>"
        book.add_item(item)
        items.append(item)
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    book.spine = ["nav", *items]
    epub.write_epub(source, book)
    return source


def _stored_as_one_chapter(tmp_path, settings):
    """A book the old splitter stored as one chapter, with a B2 adaptation mirroring it."""

    settings.MEDIA_ROOT = tmp_path / "media"
    path = _epub(tmp_path)
    work = Work.objects.create(slug="pride", title="Pride and Prejudice", author="Jane Austen")
    source = Edition.objects.create(
        work=work, slug="pride-en", title="Pride and Prejudice", author="Jane Austen", language="en"
    )
    source.source_file.save("pride.epub", ContentFile(path.read_bytes()))
    artifact = ingest_epub(path, edition_slug="pride-en", work_slug="pride")
    glued = artifact.model_copy(
        update={
            "blocks": [
                block.model_copy(update={"chapter": 0, "seq": index, "block_id": f"c0.x{index}"})
                for index, block in enumerate(artifact.blocks, 1)
            ]
        }
    )
    run = PipelineRun.objects.create(
        edition=source,
        stage="ingest",
        processor_version="0.2.0",
        input_hash="",
        idempotency_key="old-ingest",
        status="succeeded",
    )
    persist_artifact(source, glued, run)
    # the adaptation mirrors the source block for block, chapter for chapter
    adaptation = Edition.objects.create(
        work=work,
        slug="pride-en-b2",
        language="en",
        edition_type=Edition.EditionType.ADAPTATION,
        source_edition=source,
        status=Edition.Status.READY,
    )
    chapter = Chapter.objects.create(edition=adaptation, sequence=0)
    for block in source.blocks.order_by("sequence"):
        ContentBlock.objects.create(
            edition=adaptation,
            chapter=chapter,
            block_id=block.block_id,
            sequence=block.sequence,
            block_type=block.block_type,
            text=f"Simpler: {block.text}",
        )
    return source, adaptation


def test_a_recut_moves_the_paragraphs_and_the_adaptation_without_rewriting(tmp_path, settings):
    source, adaptation = _stored_as_one_chapter(tmp_path, settings)
    assert source.chapters.count() == 1 and adaptation.chapters.count() == 1
    before = {b.block_id: b.text for b in adaptation.blocks.all()}

    plan = plan_recut(source)

    assert (plan.old_chapters, plan.new_chapters) == (1, 3)
    assert plan.matched == plan.stored_text_blocks == 9
    assert not plan.material_change and not plan.unchanged
    assert [title for _, title, _ in plan.chapters] == ["Chapter I", "Chapter II", "Chapter III"]

    run = apply_recut(plan)

    for edition in (source, adaptation):
        chapters = list(edition.chapters.order_by("sequence"))
        assert [c.title for c in chapters] == ["Chapter I", "Chapter II", "Chapter III"]
        assert [c.blocks.count() for c in chapters] == [3, 3, 3]
        assert [b.sequence for b in chapters[1].blocks.order_by("sequence")] == [1, 2, 3]
    # not a word changed, and the adaptation's paragraphs sit where their source paragraphs do
    assert {b.block_id: b.text for b in adaptation.blocks.all()} == before
    pairs = {b.block_id: b.chapter.sequence for b in adaptation.blocks.select_related("chapter")}
    assert pairs == {
        b.block_id: b.chapter.sequence for b in source.blocks.select_related("chapter")
    }
    assert run.summary["recut"] and run.summary["new_chapters"] == 3
    assert "+cut-" in run.processor_version


def test_a_file_whose_text_changed_is_not_recut(tmp_path, settings):
    source, _ = _stored_as_one_chapter(tmp_path, settings)
    ContentBlock.objects.filter(edition=source, block_type="paragraph").update(text="Rewritten.")

    plan = plan_recut(source)

    assert plan.material_change
    assert len(plan.unmatched_stored) == 6


def test_a_book_already_cut_this_way_is_left_alone(tmp_path, settings):
    source, _ = _stored_as_one_chapter(tmp_path, settings)
    apply_recut(plan_recut(source))

    plan = plan_recut(source)

    assert plan.unchanged


def test_a_long_run_of_new_text_does_not_leave_later_paragraphs_unmatched(tmp_path, settings):
    # Pride and Prejudice's illustrated edition: a list of sixty plates the old reader skipped,
    # then the whole novel; a lookahead of eighty fresh paragraphs lost all but 31 of 2,256
    from almonium_book_processor.catalog.recut import _match

    source, _ = _stored_as_one_chapter(tmp_path, settings)
    artifact = ingest_epub(_epub(tmp_path), edition_slug="pride-en", work_slug="pride")
    plates = [
        artifact.blocks[1].model_copy(
            update={"chapter": 0, "block_id": f"c0.pl{n}", "seq": 100 + n, "text": f"Plate {n}"}
        )
        for n in range(200)
    ]
    padded = artifact.model_copy(
        update={"blocks": [artifact.blocks[0], *plates, *artifact.blocks[1:]]}
    )

    plan = _match(source, padded, "sha")

    assert plan.matched == plan.stored_text_blocks == 9
    assert len(plan.unmatched_fresh) == 200 and not plan.unmatched_stored
