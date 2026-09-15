from types import SimpleNamespace
from unittest.mock import patch

import pytest

from almonium_book_processor.catalog.models import AIRun, PipelineRun
from almonium_book_processor.catalog.offline_sentence_alignment import (
    queue_alignment,
    run_alignment,
)
from almonium_book_processor.catalog.parallel_content import inherited_payload
from almonium_book_processor.processing.sentence_correspondence import correspond
from tests.catalog.test_sentence_alignment import pair  # noqa: F401

pytestmark = pytest.mark.django_db


def test_offline_job_caches_inverts_and_keeps_review_status(pair, monkeypatch):  # noqa: F811
    p, s = pair
    s.status = "review"
    s.save()
    with patch(
        "almonium_book_processor.processing.sentence_correspondence.embed_texts",
        return_value=[[1, 0], [0, 1], [1, 0], [0, 1]],
    ) as encode:
        run = queue_alignment(p.id, s.id)
        run_alignment(run.id)
        assert encode.call_count == 1
        assert queue_alignment(p.id, s.id).id == run.id
        run_alignment(run.id)
        assert encode.call_count == 1
    run.refresh_from_db()
    assert run.status == PipelineRun.Status.SUCCEEDED
    assert run.summary["completed_blocks"] == 1
    assert not AIRun.objects.exists()
    assert inherited_payload(p, s)["blocks"][0]["sentence_alignment"]
    assert inherited_payload(s, p)["blocks"][0]["sentence_alignment"]
    s.refresh_from_db()
    assert s.status == "review"
    s.blocks.update(text="Changed.")
    assert inherited_payload(p, s)["blocks"][0]["sentence_alignment"] == []


def test_changed_source_fails_without_provider_call(pair):  # noqa: F811
    p, s = pair
    run = queue_alignment(p.id, s.id)
    p.blocks.update(text="Changed.")
    with pytest.raises(ValueError, match="changed"):
        run_alignment(run.id)
    run.refresh_from_db()
    assert run.status == "failed"
    assert not p.artifacts.exists()


def test_invalid_offsets_refuse_alignment(pair):  # noqa: F811
    p, s = pair
    p.blocks.update(sentences=[{"start": 0, "end": 999}])
    with pytest.raises(ValueError, match="offsets"):
        correspond(p.blocks.get(), s.blocks.get())


def test_uncertain_correspondence_covers_each_index_without_highlights(pair):  # noqa: F811
    p, s = pair
    with patch(
        "almonium_book_processor.processing.sentence_correspondence.embed_texts",
        return_value=[[1, 0], [1, 0], [0, 1], [0, 1]],
    ):
        payload = correspond(p.blocks.get(), s.blocks.get())
    assert not any(g["certain"] for g in payload["groups"])
    for side in ("primary", "secondary"):
        assert sorted(i for g in payload["groups"] for i in g[side]) == [0, 1]


def test_one_to_three_and_oversized_fallback():
    p = SimpleNamespace(text="One two three.", sentences=[{"start": 0, "end": 14}])
    s = SimpleNamespace(
        text="One. Two. Three.",
        sentences=[{"start": 0, "end": 4}, {"start": 5, "end": 9}, {"start": 10, "end": 16}],
    )
    with patch(
        "almonium_book_processor.processing.sentence_correspondence.embed_texts",
        return_value=[[1, 1, 1], [1, 0, 0], [0, 1, 0], [0, 0, 1]],
    ):
        payload = correspond(p, s)
    assert payload["groups"][0]["primary"] == [0]
    assert payload["groups"][0]["secondary"] == [0, 1, 2]
    with patch(
        "almonium_book_processor.processing.sentence_correspondence.embed_texts",
        side_effect=ValueError("Sentence exceeds embedding token limit"),
    ):
        assert correspond(p, s)["method"] == "paragraph_fallback"


def test_offline_queue_is_staff_post_only(client, pair):  # noqa: F811
    from django.contrib.auth import get_user_model

    p, s = pair
    url = f"/editions/{p.id}/sentence-preview/{s.id}/"
    assert client.post(url).status_code == 302
    assert not PipelineRun.objects.exists()
    client.force_login(get_user_model().objects.create_user(username="offline", is_staff=True))
    assert client.get(url).status_code == 200
    assert not PipelineRun.objects.exists()
    assert client.post(url).status_code == 302
    assert PipelineRun.objects.count() == 1
