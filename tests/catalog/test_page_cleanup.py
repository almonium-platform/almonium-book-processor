from io import BytesIO
from unittest.mock import patch
from zipfile import ZipFile

import pytest
from django.core.files.base import ContentFile

from almonium_book_processor.catalog.image_cleanup import _sentence_hash
from almonium_book_processor.catalog.models import AIRun, PipelineRun
from almonium_book_processor.catalog.offline_sentence_alignment import queue_alignment
from almonium_book_processor.catalog.page_cleanup import apply_page_cleanup, plan_page_cleanup
from tests.catalog.test_sentence_alignment import pair  # noqa: F401

pytestmark = pytest.mark.django_db


def test_cleanup_requires_source_markup_and_archives_old_spans(pair, settings, tmp_path):  # noqa: F811
    settings.MEDIA_ROOT = tmp_path
    original, companion = pair
    source = BytesIO()
    with ZipFile(source, "w") as archive:
        archive.writestr(
            "EPUB/chapter.xhtml",
            '<p>She said [1] <span class="tei-pb">[pg 79]</span>goodbye.</p>',
        )
    original.source_file.save("source.epub", ContentFile(source.getvalue()))
    original.blocks.update(
        source_ref="chapter.xhtml",
        text="She said [1] [pg 79]goodbye.",
        sentences=[{"start": 0, "end": 27}],
    )
    companion.blocks.update(text="He said [1] [pg 79] goodbye.")
    run = queue_alignment(original.pk, companion.pk)
    PipelineRun.objects.filter(pk=run.pk).update(status=PipelineRun.Status.SUCCEEDED)
    old_hash = _sentence_hash(original)
    PipelineRun.objects.create(
        edition=original,
        stage="sentences",
        status="succeeded",
        idempotency_key="old split",
        processor_version="test",
        input_hash=old_hash,
    )

    edits, counts = plan_page_cleanup()
    assert counts["source EPUBs scanned"] == 1
    assert len(edits) == 2
    assert original.blocks.get().text == "She said [1] [pg 79]goodbye."
    with patch(
        "almonium_book_processor.catalog.page_cleanup.split_sentences",
        side_effect=lambda text, language: [text],
    ):
        stats = apply_page_cleanup(edits)
    assert stats["blocks cleaned"] == 2
    assert stats["changed aligned paragraph pairs"] == 1
    block = original.blocks.get()
    assert block.text == "She said [1] goodbye."
    assert block.attributes["legacy_page_text"]["text"] == "She said [1] [pg 79]goodbye."
    assert block.sentences == [{"id": "c11.p1.s1", "start": 0, "end": len(block.text)}]
    assert companion.blocks.get().text == "He said [1] goodbye."
    assert PipelineRun.objects.filter(
        stage="align", status="queued", summary__local_only=True
    ).exists()
    assert PipelineRun.objects.filter(
        stage="sentences", input_hash=_sentence_hash(original)
    ).exists()
    assert plan_page_cleanup()[0] == []
    assert not AIRun.objects.exists()


def test_a_shared_footnote_number_is_left_in_a_reworded_companion(pair, settings, tmp_path):  # noqa: F811
    settings.MEDIA_ROOT = tmp_path
    original, companion = pair
    source = BytesIO()
    with ZipFile(source, "w") as archive:
        archive.writestr(
            "chapter.xhtml",
            '<p>He [9] offered <span class="pagenum">[9]</span> tea.</p>',
        )
    original.source_file.save("source.epub", ContentFile(source.getvalue()))
    original.blocks.update(source_ref="chapter.xhtml", text="He [9] offered [9] tea.")
    companion.blocks.update(text="I [9] offered [9] tea.")
    edits, _ = plan_page_cleanup()
    assert [(edit.block.edition_id, edit.text) for edit in edits] == [
        (original.pk, "He [9] offered tea.")
    ]
