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


def test_distinct_lower_score_matches_highlight_but_ambiguous_ones_do_not(pair):  # noqa: F811
    p, s = pair
    # Both true matches score below the old threshold, with distinct alternatives.
    with patch(
        "almonium_book_processor.processing.sentence_correspondence.embed_texts",
        return_value=[[1, 0, 0], [0, 1, 0], [0.79, 0, 0.613], [0, 0.79, 0.613]],
    ):
        payload = correspond(p.blocks.get(), s.blocks.get())
    assert all(g["certain"] for g in payload["groups"])
    assert all(g["acceptance"] == "reciprocal_margin" for g in payload["groups"])
    with patch(
        "almonium_book_processor.processing.sentence_correspondence.embed_texts",
        return_value=[[1, 0], [1, 0], [0.79, 0.613], [0.79, 0.613]],
    ):
        payload = correspond(p.blocks.get(), s.blocks.get())
    assert not any(g["certain"] for g in payload["groups"])


def test_chunking_preserves_all_text_and_never_exceeds_encoder_window(monkeypatch):
    from almonium_book_processor.processing import nlp

    class Tokenizer:
        def __call__(self, text, **kwargs):
            return {"input_ids": [0] + list(text) + [0]}

        def num_special_tokens_to_add(self):
            return 2

    class Model:
        tokenizer = Tokenizer()
        max_seq_length = 10

        def encode(self, texts, **kwargs):
            assert all(len(text) + 2 <= self.max_seq_length for text in texts)
            self.texts = texts
            return [[1, 0] if "a" in text else [0, 1] for text in texts]

    model = Model()
    monkeypatch.setattr(nlp, "_embedding_model", lambda _: model)
    texts = ["aaaaaaaa bbbbbbbb", "cc"]
    vectors = nlp.embed_texts(texts, chunk_long=True)
    assert "".join(model.texts) == "".join(texts)
    assert len(vectors) == 2
    assert vectors[0][0] > 0 and vectors[0][1] > 0
    assert sum(v * v for v in vectors[0]) == pytest.approx(1)
    assert vectors[1] == [0, 1]


def test_semicolon_clauses_refine_without_changing_text_or_sentence_spans():
    from almonium_book_processor.processing.sentence_correspondence import clause_spans

    p = SimpleNamespace(
        text="Yellow skin; black hair; white teeth.", sentences=[{"start": 0, "end": 36}]
    )
    s = SimpleNamespace(
        text="Жовта шкіра; чорне волосся; білі зуби.", sentences=[{"start": 0, "end": 36}]
    )
    # Use exact lengths, not byte lengths for Unicode.
    p.sentences[0]["end"] = len(p.text)
    s.sentences[0]["end"] = len(s.text)
    spans = clause_spans(p)
    assert [p.text[x["start"] : x["end"]] for x in spans] == [
        "Yellow skin;",
        "black hair;",
        "white teeth.",
    ]
    with patch(
        "almonium_book_processor.processing.sentence_correspondence.embed_texts",
        return_value=[[1, 0, 0], [0, 1, 0], [0, 0, 1]] * 2,
    ):
        result = correspond(p, s, model_name="sentence-transformers/LaBSE")
    assert len(result["groups"]) == 3
    assert all(g["certain"] and g["granularity"] == "clause" for g in result["groups"])
    assert len(p.sentences) == 1
    with patch(
        "almonium_book_processor.processing.sentence_correspondence.embed_texts",
        return_value=[[1, 0]] * 3 + [[0, 1]] * 3,
    ):
        result = correspond(p, s)
    assert len(result["groups"]) == 1
    assert result["groups"][0]["certain"]
    assert result["groups"][0]["primary"] == [0, 1, 2]
    assert result["groups"][0]["granularity"] == "sentence"


def test_model_selection_is_versioned_and_invalid_model_rejected(pair):  # noqa: F811
    p, s = pair
    first = queue_alignment(p.id, s.id)
    second = queue_alignment(p.id, s.id, model="sentence-transformers/LaBSE")
    assert first.processor_version != second.processor_version
    assert first.id != second.id
    assert second.summary["model"] == "sentence-transformers/LaBSE"
    with pytest.raises(ValueError, match="supported"):
        queue_alignment(p.id, s.id, model="https://arbitrary-model")


def test_clause_spans_invert_and_edits_invalidate(pair):  # noqa: F811
    from almonium_book_processor.catalog.models import EditionArtifact
    from almonium_book_processor.catalog.offline_sentence_alignment import processor_version
    from almonium_book_processor.catalog.parallel_content import pair_hash

    p, s = pair
    a, b = p.blocks.get(), s.blocks.get()
    EditionArtifact.objects.create(
        edition=p,
        kind="sentence_alignment",
        input_hash=pair_hash(a, b),
        processor_version=processor_version(),
        payload={
            "model": "test-model",
            "primary_spans": [{"start": 0, "end": len(a.text)}],
            "secondary_spans": b.sentences,
            "groups": [{"primary": [0], "secondary": [0, 1], "certain": True}],
        },
    )
    reverse = inherited_payload(s, p)["blocks"][0]
    assert reverse["primary_sentences"] == b.sentences
    assert reverse["secondary_sentences"] == [{"start": 0, "end": len(a.text)}]
    assert reverse["sentence_alignment"][0]["primary"] == [0, 1]
    assert reverse["alignment_provenance"]["model"] == "test-model"
    p.blocks.update(text="New text.")
    assert inherited_payload(s, p)["blocks"][0]["alignment_provenance"] is None


def test_newer_reverse_model_result_wins_over_older_direct(pair):  # noqa: F811
    from almonium_book_processor.catalog.parallel_content import aligned_data, pair_hash

    p, s = (e.blocks.get() for e in pair)
    artifacts = {
        pair_hash(p, s): {"groups": [], "provenance": {"created_at": "2026-09-15"}},
        pair_hash(s, p): {
            "groups": [{"primary": [0, 1], "secondary": [0], "certain": True}],
            "provenance": {"created_at": "2026-09-16"},
        },
    }
    result = aligned_data(artifacts, p, s)
    assert result["groups"][0]["primary"] == [0]
    assert result["provenance"]["created_at"] == "2026-09-16"


def test_one_uncertain_clause_does_not_hide_other_confident_clauses():
    p = SimpleNamespace(text="Yellow skin; black hair; white teeth.", sentences=[])
    s = SimpleNamespace(text="Жовта шкіра; чорне волосся; білі зуби.", sentences=[])
    for block in [p, s]:
        block.sentences = [{"start": 0, "end": len(block.text)}]
    with patch(
        "almonium_book_processor.processing.sentence_correspondence.embed_texts",
        return_value=[
            [1, 0, 0, 0],
            [0, 1, 0, 0],
            [0, 0, 1, 0],
            [1, 0, 0, 0],
            [0, 1, 0, 0],
            [0, 0, 0.70, 0.714],
        ],
    ):
        result = correspond(p, s)
    assert len(result["groups"]) == 3
    assert [g["certain"] for g in result["groups"]] == [True, True, False]
    assert result["groups"][0]["primary"] == [0]
