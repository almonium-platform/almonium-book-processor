from io import StringIO
from unittest.mock import patch

import pytest
from django.core.management import call_command

from almonium_book_processor.catalog.models import PipelineRun
from tests.catalog.test_sentence_alignment import pair  # noqa: F401

pytestmark = pytest.mark.django_db


def spans(text, pieces):
    result, cursor = [], 0
    for number, piece in enumerate(pieces, 1):
        start = text.index(piece, cursor)
        result.append({"id": f"c11.p1.s{number}", "start": start, "end": start + len(piece)})
        cursor = start + len(piece)
    return result


def test_sentence_splitting_folds_a_lone_mark_into_its_sentence(pair):  # noqa: F811
    from almonium_book_processor.catalog.tasks import split_edition_sentences

    original, _ = pair
    original.blocks.update(text="« Hello. » Again.")
    with patch(
        "almonium_book_processor.catalog.tasks.split_sentences",
        return_value=["«", "Hello.", "»", "Again."],
    ):
        split_edition_sentences(str(original.id))
    block = original.blocks.get()
    assert block.sentences == [
        {"id": "c11.p1.s1", "start": 0, "end": 10},
        {"id": "c11.p1.s2", "start": 11, "end": 17},
    ]
    assert original.pipeline_runs.get(stage="sentences").summary["sentences"] == 2


def test_the_repair_folds_only_blocks_with_lone_marks_and_queues_their_alignment(pair):  # noqa: F811
    original, adapted = pair
    text = "« Bonjour. » Encore."
    original.blocks.update(text=text, sentences=spans(text, ["«", "Bonjour.", "»", "Encore."]))
    untouched = adapted.blocks.get().sentences

    out = StringIO()
    call_command("repair_sentence_punctuation", "--dry-run", stdout=out)
    assert "en: would fold 2 punctuation-only sentence(s) in 1 block(s)" in out.getvalue()
    assert len(original.blocks.get().sentences) == 4
    assert not PipelineRun.objects.filter(stage="align").exists()

    out = StringIO()
    call_command("repair_sentence_punctuation", stdout=out)
    assert original.blocks.get().sentences == [
        {"id": "c11.p1.s1", "start": 0, "end": 12},
        {"id": "c11.p1.s2", "start": 13, "end": 20},
    ]
    assert adapted.blocks.get().sentences == untouched
    assert "1 edition(s) changed; 1 alignment run(s) queued." in out.getvalue()

    out = StringIO()
    call_command("repair_sentence_punctuation", stdout=out)
    assert "0 edition(s) changed" in out.getvalue()
