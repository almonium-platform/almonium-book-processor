import uuid
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from almonium_book_processor.catalog import services
from almonium_book_processor.catalog.models import (
    Chapter,
    ContentBlock,
    Edition,
    PipelineRun,
    Work,
)
from almonium_book_processor.catalog.offline_sentence_alignment import (
    queue_alignment,
    run_alignment,
)
from almonium_book_processor.catalog.parallel_content import inherited_payload
from almonium_book_processor.catalog.parallel_status import (
    companion_rows,
    pair_status,
    refresh_sentence_alignment,
)
from almonium_book_processor.catalog.tasks import refresh_edition_after_revision

pytestmark = pytest.mark.django_db

VECTORS = [[1, 0], [0, 1], [1, 0], [0, 1]]
EMBED = "almonium_book_processor.processing.sentence_correspondence.embed_texts"


def spans(text):
    """Two one-word sentences separated by a space."""

    first, second = text.split(" ")
    return [{"start": 0, "end": len(first)}, {"start": len(first) + 1, "end": len(text)}]


@pytest.fixture
def tree():
    """A canonical original with an adaptation and a translation, two blocks each."""

    work = Work.objects.create(slug="tree", title="Book")
    original = Edition.objects.create(
        work=work, slug="original", language="en", parallel_role="canonical", status="published"
    )
    adapted = Edition.objects.create(
        work=work,
        slug="adapted",
        language="en",
        cefr_level="B2",
        edition_type="adaptation",
        source_edition=original,
        parallel_role="parallel",
        status="published",
    )
    ukrainian = Edition.objects.create(
        work=work,
        slug="ukrainian",
        language="uk",
        edition_type="machine_translation",
        source_edition=original,
        parallel_role="parallel",
        status="published",
    )
    groups = [uuid.uuid4(), uuid.uuid4()]
    for edition, texts in (
        (original, ("Hello. Again.", "Night. Falls.")),
        (adapted, ("Hello! Again.", "Night! Falls.")),
        (ukrainian, ("Привіт. Знову.", "Ніч. Падає.")),
    ):
        chapter = Chapter.objects.create(edition=edition, sequence=1, title="I")
        for index, text in enumerate(texts):
            ContentBlock.objects.create(
                edition=edition,
                chapter=chapter,
                block_id=f"c1.p{index + 1}",
                sequence=index + 1,
                align_group=groups[index],
                text=text,
                sentences=spans(text),
            )
    return original, adapted, ukrainian


def align(primary, secondary, model=None):
    with patch(EMBED, return_value=VECTORS):
        run = queue_alignment(primary.id, secondary.id, model=model)
        run_alignment(run.id)
    run.refresh_from_db()
    assert run.status == PipelineRun.Status.SUCCEEDED
    return run


def revise(edition, block, text):
    editor = get_user_model().objects.create_user(username=f"editor-{uuid.uuid4()}", is_staff=True)
    with patch("almonium_book_processor.catalog.tasks.refresh_edition_after_revision.delay"):
        services.revise_block_text(
            edition=edition, block_id=block.id, revised_text=text, editor=editor
        )
    # The refresh task re-splits the corrected block; emulate the split so
    # the other block keeps its digest and can be served from cache.
    ContentBlock.objects.filter(pk=block.id).update(sentences=spans(text))


def test_pair_status_moves_from_missing_to_current_to_stale(tree):
    original, adapted, ukrainian = tree
    assert pair_status(adapted, ukrainian)["state"] == "missing"

    align(adapted, ukrainian, model="sentence-transformers/LaBSE")
    status = pair_status(adapted, ukrainian)
    assert (status["state"], status["current"], status["total"]) == ("current", 2, 2)
    assert status["model"] == "sentence-transformers/LaBSE"
    # The reverse orientation reads the same artifacts.
    assert pair_status(ukrainian, adapted)["state"] == "current"

    revise(adapted, adapted.blocks.get(block_id="c1.p1"), "Hullo! Again.")
    status = pair_status(adapted, ukrainian)
    assert status["state"] == "stale"
    assert (status["current"], status["reusable"], status["changed"]) == (0, 1, 1)
    assert inherited_payload(adapted, ukrainian)["blocks"][1]["sentence_alignment"] == []


def test_companion_rows_cover_every_parallel_sibling(tree):
    original, adapted, ukrainian = tree
    rows = companion_rows(adapted)
    assert [row["other"].slug for row in rows] == ["original", "ukrainian"]
    assert all(row["complete"] for row in rows)
    standalone = Edition.objects.create(
        work=original.work, slug="french", language="fr", parallel_role="standalone"
    )
    assert standalone.slug not in [row["other"].slug for row in companion_rows(adapted)]
    assert companion_rows(standalone) == []


def test_revision_refresh_requeues_only_pairs_that_were_aligned(tree):
    original, adapted, ukrainian = tree
    first = align(adapted, ukrainian, model="sentence-transformers/LaBSE")
    revise(adapted, adapted.blocks.get(block_id="c1.p1"), "Hullo! Again.")

    queued = refresh_sentence_alignment(adapted)

    assert [run.summary["secondary_id"] for run in queued] == [str(ukrainian.id)]
    run = queued[0]
    assert run.status == PipelineRun.Status.QUEUED
    assert run.edition_id == first.edition_id
    assert run.summary["model"] == "sentence-transformers/LaBSE"
    assert run.id != first.id
    # The original was never sentence-aligned with the adaptation: no new job.
    assert pair_status(adapted, original)["state"] == "missing"
    assert not PipelineRun.objects.filter(summary__secondary_id=str(original.id)).exists()

    # Running the queued job embeds only the changed block.
    with patch(EMBED, return_value=VECTORS) as encode:
        run_alignment(run.id)
    assert encode.call_count == 1
    assert pair_status(adapted, ukrainian)["state"] == "current"


def test_refresh_task_keeps_the_orientation_of_the_last_job(tree, monkeypatch):
    original, adapted, ukrainian = tree
    first = align(ukrainian, adapted)
    for name in (
        "split_edition_sentences",
        "analyze_edition_lexicon",
        "analyze_edition_source_quality",
    ):
        monkeypatch.setattr(
            f"almonium_book_processor.catalog.tasks.{name}.run", lambda edition_id: None
        )
    revise(adapted, adapted.blocks.get(block_id="c1.p2"), "Night! Comes.")

    refresh_edition_after_revision.run(str(adapted.id))

    runs = PipelineRun.objects.filter(stage="align").exclude(pk=first.pk)
    assert runs.count() == 1
    assert runs.get().edition_id == ukrainian.id
    assert runs.get().status == PipelineRun.Status.QUEUED


def test_reverted_text_serves_the_succeeded_run_again(tree):
    original, adapted, ukrainian = tree
    first = align(adapted, ukrainian)
    block = adapted.blocks.get(block_id="c1.p1")
    revise(adapted, block, "Hullo! Again.")
    revise(adapted, block, "Hello! Again.")
    assert pair_status(adapted, ukrainian)["state"] == "stale"

    with patch(EMBED, return_value=VECTORS) as encode:
        run = queue_alignment(adapted.id, ukrainian.id)
        assert run.id == first.id
        assert run.status == PipelineRun.Status.QUEUED
        run_alignment(run.id)
    assert encode.call_count == 0
    assert pair_status(adapted, ukrainian)["state"] == "current"


def test_edition_page_shows_the_companion_table_and_queues_from_it(client, tree):
    original, adapted, ukrainian = tree
    align(adapted, ukrainian, model="sentence-transformers/LaBSE")
    revise(adapted, adapted.blocks.get(block_id="c1.p1"), "Hullo! Again.")
    queue_url = reverse("catalog:queue-sentence-alignment", args=[adapted.id, ukrainian.id])

    assert client.post(queue_url).status_code == 302
    assert not PipelineRun.objects.filter(status="queued").exists()

    client.force_login(get_user_model().objects.create_user(username="staff", is_staff=True))
    page = client.get(reverse("catalog:edition-detail", args=[adapted.id]))
    assert page.status_code == 200
    rows = {row["other"].slug: row for row in page.context["parallel_companions"]}
    assert rows["ukrainian"]["state"] == "stale"
    assert rows["original"]["state"] == "missing"
    assert page.context["parallel_companions_due"] == 2
    html = page.content.decode()
    assert "Parallel companions" in html
    assert "1 changed since the last job" in html
    assert queue_url in html

    response = client.post(queue_url, {"model": "sentence-transformers/LaBSE"})
    assert response.status_code == 302
    assert response["Location"].endswith("#parallel-companions")
    run = PipelineRun.objects.get(status="queued")
    assert run.summary["model"] == "sentence-transformers/LaBSE"
    page = client.get(reverse("catalog:edition-detail", args=[adapted.id]))
    rows = {row["other"].slug: row for row in page.context["parallel_companions"]}
    assert rows["ukrainian"]["state"] == "running"
