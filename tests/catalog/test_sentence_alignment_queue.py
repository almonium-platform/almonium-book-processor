from io import StringIO
from unittest.mock import patch

import pytest
from django.conf import settings
from django.core.management import call_command

from almonium_book_processor.catalog.models import ContentBlock, Edition, PipelineRun
from almonium_book_processor.catalog.sentence_alignment_queue import queue_for
from tests.catalog.test_sentence_alignment import pair  # noqa: F401

pytestmark = pytest.mark.django_db


def companion(original, slug, text):
    edition = Edition.objects.create(
        work=original.work,
        slug=slug,
        language="uk",
        source_edition=original,
        parallel_role="parallel",
        status="review",
    )
    source = original.blocks.get()
    chapter = edition.chapters.create(sequence=source.chapter.sequence, title="V")
    ContentBlock.objects.create(
        edition=edition,
        chapter=chapter,
        block_id=source.block_id,
        sequence=source.sequence,
        align_group=source.align_group,
        text=text,
        sentences=[{"start": 0, "end": 6}, {"start": 7, "end": len(text)}],
    )
    return edition


def runs():
    return PipelineRun.objects.filter(idempotency_key__startswith="offline-sentence-")


def test_a_new_edition_is_queued_with_its_original_in_the_alignment_model(pair):  # noqa: F811
    original, adapted = pair
    (run,) = queue_for(adapted)
    assert run.edition_id == original.id
    assert run.summary["secondary_id"] == str(adapted.id)
    assert run.summary["model"] == settings.SENTENCE_ALIGNMENT_MODEL
    # The same text again finds the same run: nothing is queued twice.
    assert queue_for(adapted) == []
    assert runs().count() == 1


def test_an_original_queues_every_edition_made_from_it(pair):  # noqa: F811
    original, adapted = pair
    ukrainian = companion(original, "ukrainian", "Привіт. Знову.")
    queued = queue_for(original)
    assert sorted(r.summary["secondary_id"] for r in queued) == sorted(
        [str(adapted.id), str(ukrainian.id)]
    )


def test_a_private_book_and_an_incomplete_pair_are_never_queued(pair):  # noqa: F811
    original, adapted = pair
    original.work.visibility = "private"
    original.work.save()
    assert queue_for(adapted) == []
    original.work.visibility = "public"
    original.work.save()
    adapted.blocks.update(align_group=None)
    assert queue_for(adapted) == []
    assert not runs().exists()


def test_alignment_runs_on_its_own_queue():
    route = settings.CELERY_TASK_ROUTES[
        "almonium_book_processor.catalog.tasks.align_edition_sentences"
    ]
    assert route == {"queue": settings.SENTENCE_ALIGNMENT_QUEUE}


def test_finished_sentence_splitting_queues_the_edition_and_a_queuing_error_does_not_fail_it(
    pair,  # noqa: F811
):
    from almonium_book_processor.catalog.tasks import split_edition_sentences

    original, adapted = pair
    with (
        patch(
            "almonium_book_processor.catalog.tasks.split_sentences",
            side_effect=lambda text, language: text.split(" "),
        ),
        patch(
            "almonium_book_processor.catalog.sentence_alignment_queue.queue_for",
            side_effect=RuntimeError("broker away"),
        ) as queued,
    ):
        split_edition_sentences(str(adapted.id))
    assert queued.call_args.args[0].id == adapted.id
    assert adapted.pipeline_runs.get(stage="sentences").status == "succeeded"


def test_the_backfill_queues_each_pair_once(pair):  # noqa: F811
    original, adapted = pair
    out = StringIO()
    call_command("queue_sentence_alignment", "--dry-run", stdout=out)
    assert "would queue 1 pair(s)" in out.getvalue()
    assert not runs().exists()
    call_command("queue_sentence_alignment", stdout=StringIO())
    call_command("queue_sentence_alignment", stdout=out)
    assert runs().count() == 1
    assert "queued 0 pair(s)" in out.getvalue()
