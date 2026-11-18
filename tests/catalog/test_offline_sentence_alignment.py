import uuid
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from almonium_book_processor.catalog.models import AIRun, PipelineRun
from almonium_book_processor.catalog.offline_sentence_alignment import (
    queue_alignment,
    run_alignment,
)
from almonium_book_processor.catalog.parallel_content import inherited_payload
from almonium_book_processor.processing import sentence_correspondence
from almonium_book_processor.processing.sentence_correspondence import _cover_groups, correspond
from tests.catalog.test_sentence_alignment import pair  # noqa: F401

pytestmark = pytest.mark.django_db

HELLO = {"Hello.": [1, 0], "Hello!": [1, 0], "Again.": [0, 1]}


def hello(texts, **_):
    """The pair fixture's sentences by text: a run asks for each distinct text once."""

    return [HELLO[text.strip()] for text in texts]


def test_offline_job_caches_inverts_and_keeps_review_status(pair, monkeypatch):  # noqa: F811
    p, s = pair
    s.status = "review"
    s.save()
    with patch(
        "almonium_book_processor.processing.sentence_correspondence.embed_texts",
        side_effect=hello,
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
    assert all(g["primary"] and g["secondary"] for g in payload["groups"])
    for side in ("primary", "secondary"):
        assert sorted(i for g in payload["groups"] for i in g[side]) == [0, 1]


def test_unmatched_prefix_is_attached_to_the_first_pair():
    groups = _cover_groups(4, 2, [{"primary": [2, 3], "secondary": [0, 1], "certain": True}])
    assert groups == [{"primary": [0, 1, 2, 3], "secondary": [0, 1], "certain": False}]


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
    sentence_correspondence._vectors.clear()  # the model's failure, not a remembered answer
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
    sentence_correspondence._vectors.clear()  # a second, hypothetical model of the same text
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
            if isinstance(text, list):  # a batch, as the real tokenizer takes one
                return {"input_ids": [[0, *item, 0] for item in text]}
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
    [spans] = clause_spans(p)
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


def test_a_weak_clause_merges_with_its_neighbour_and_the_rest_stay_apart():
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
            [0, 0.5, 0.4, 0.768],
        ],
    ):
        result = correspond(p, s)
    assert [(g["primary"], g["secondary"]) for g in result["groups"]] == [
        ([0], [0]),
        ([1, 2], [1, 2]),
    ]
    assert all(g["granularity"] == "clause" for g in result["groups"])


def test_comma_clauses_keep_list_items_whole_and_a_german_verb_with_its_clause():
    from almonium_book_processor.processing.sentence_correspondence import clause_spans

    def chunks(text):
        block = SimpleNamespace(text=text, sentences=[{"start": 0, "end": len(text)}])
        return [text[x["start"] : x["end"]] for x in clause_spans(block)[0]]

    assert chunks(
        "Als die Droschke vor der angegebenen Adresse hielt, hob sich der Nebel ein wenig."
    ) == ["Als die Droschke vor der angegebenen Adresse hielt,", "hob sich der Nebel ein wenig."]
    assert chunks("Spiel, Trotz, Genuß ist übrigens darin!") == [
        "Spiel, Trotz, Genuß ist übrigens darin!"
    ]
    assert chunks("He caught up the next paper; it was a note.") == [
        "He caught up the next paper;",
        "it was a note.",
    ]


def test_a_crossing_clause_order_is_not_split():
    p = SimpleNamespace(
        text="When he arrived at the house, it was raining very hard.", sentences=[]
    )
    s = SimpleNamespace(text="Es regnete sehr stark, als er beim Haus ankam.", sentences=[])
    for block in [p, s]:
        block.sentences = [{"start": 0, "end": len(block.text)}]
    with patch(
        "almonium_book_processor.processing.sentence_correspondence.embed_texts",
        return_value=[[1, 0.2], [0.2, 1], [0.25, 1], [1, 0.25]],
    ):
        result = correspond(p, s)
    assert [(g["primary"], g["secondary"]) for g in result["groups"]] == [([0, 1], [0, 1])]
    assert result["groups"][0]["granularity"] == "sentence"


def test_paragraph_view_tints_each_group_alike_on_both_sides(client, pair):  # noqa: F811
    from django.contrib.auth import get_user_model

    p, s = pair
    with patch(
        "almonium_book_processor.processing.sentence_correspondence.embed_texts",
        side_effect=hello,
    ):
        run_alignment(queue_alignment(p.id, s.id).id)
    client.force_login(get_user_model().objects.create_user(username="tints", is_staff=True))
    page = client.get(f"/editions/{p.id}/sentence-preview/{s.id}/?chapter=11&view=paragraphs")
    html = page.content.decode()
    assert page.status_code == 200
    assert html.count('class="chunk tint-0" data-g="1"') == 2
    assert html.count('class="chunk tint-1" data-g="2"') == 2
    assert ">Hello.</span> <span" in html  # the space between chunks is kept, outside them
    assert 'data-align-filter="low"' not in html


def test_chunks_find_partners_across_a_sentence_boundary_the_languages_draw_apart():
    def block(text, ends):
        starts = [0, *[e + 1 for e in ends[:-1]]]
        return SimpleNamespace(
            text=text, sentences=[{"start": a, "end": b} for a, b in zip(starts, ends, strict=True)]
        )

    p_text = "One two three four, five six seven eight. Nine ten eleven twelve."
    s_text = "Uno dos tres cuatro. Cinco seis siete ocho, nueve diez once doce."
    p = block(p_text, [p_text.index(".") + 1, len(p_text)])
    s = block(s_text, [s_text.index(".") + 1, len(s_text)])
    vectors = {
        # Sentences: the first English one holds a chunk the Spanish puts in its second.
        "One two three four, five six seven eight.": [1, 1, 0],
        "Uno dos tres cuatro.": [1, 0, 0],
        "Cinco seis siete ocho, nueve diez once doce.": [0, 1, 1],
        # Chunks
        "One two three four,": [1, 0, 0],
        "five six seven eight.": [0, 1, 0],
        "Nine ten eleven twelve.": [0, 0, 1],
        "Cinco seis siete ocho,": [0, 1, 0],
        "nueve diez once doce.": [0, 0, 1],
    }
    with patch(
        "almonium_book_processor.processing.sentence_correspondence.embed_texts",
        side_effect=lambda texts, **_: [vectors[t.strip()] for t in texts],
    ):
        result = correspond(p, s)
    assert [(g["primary"], g["secondary"], g["certain"]) for g in result["groups"]] == [
        ([0], [0], True),
        ([1], [1], True),
        ([2], [2], True),
    ]


def test_a_run_embeds_its_paragraphs_ahead_in_one_call_and_records_how(pair):  # noqa: F811
    from almonium_book_processor.catalog.models import ContentBlock

    p, s = pair
    for edition in (p, s):
        chapter = edition.chapters.get()
        for number, text in ((2, "Hello. Again."), (3, "Hello. Again.")):
            ContentBlock.objects.create(
                edition=edition,
                chapter=chapter,
                block_id=f"c11.p{number}",
                sequence=number,
                align_group=uuid.uuid5(uuid.NAMESPACE_URL, f"group-{number}"),
                text=text if edition == p else text.replace(".", "!", 1),
                sentences=[{"start": 0, "end": 6}, {"start": 7, "end": 13}],
            )
    with patch(
        "almonium_book_processor.processing.sentence_correspondence.embed_texts",
        side_effect=hello,
    ) as encode:
        run = queue_alignment(p.id, s.id)
        run_alignment(run.id)
    # Three paragraph pairs, one call: each distinct text asked for once.
    assert encode.call_count == 1
    assert sorted(encode.call_args.args[0]) == ["Again.", "Hello!", "Hello."]
    run.refresh_from_db()
    assert run.status == PipelineRun.Status.SUCCEEDED
    assert set(run.summary["embedding"]) == {"device", "precision"}
    block = inherited_payload(p, s)["blocks"][0]
    assert block["sentence_alignment"]


def test_a_second_companion_reuses_the_original_the_worker_already_embedded(pair):  # noqa: F811
    from almonium_book_processor.catalog.models import Chapter, ContentBlock, Edition

    p, s = pair
    other = Edition.objects.create(
        work=p.work,
        slug="other",
        language="en",
        source_edition=p,
        parallel_role="parallel",
        status="published",
    )
    source = p.blocks.get()
    ContentBlock.objects.create(
        edition=other,
        chapter=Chapter.objects.create(edition=other, sequence=11, title="V"),
        block_id="c11.p1",
        sequence=1,
        align_group=source.align_group,
        text="Hello? Again.",
        sentences=[{"start": 0, "end": 6}, {"start": 7, "end": 13}],
    )
    with patch(
        "almonium_book_processor.processing.sentence_correspondence.embed_texts",
        side_effect=lambda texts, **_: [HELLO.get(t.strip(), [1, 0]) for t in texts],
    ) as encode:
        run_alignment(queue_alignment(p.id, s.id).id)
        run_alignment(queue_alignment(p.id, other.id).id)
    assert encode.call_args_list[1].args[0] == ["Hello?"]


def _refine_as_it_was(primary, secondary, p_texts, s_texts):
    """The v9 merge loop, which compared every pairing in the region: the reference."""
    import numpy as np

    from almonium_book_processor.processing.nlp import align_embeddings
    from almonium_book_processor.processing.sentence_correspondence import (
        CHUNK_MINIMUM_MARGIN,
        CHUNK_MINIMUM_SIMILARITY,
    )

    primary, secondary = np.asarray(primary, float), np.asarray(secondary, float)

    def unit(matrix, indexes):
        mean = matrix[indexes].mean(axis=0)
        norm = np.linalg.norm(mean)
        return mean / norm if norm else mean

    def similarity(group):
        return float(unit(primary, group[0]) @ unit(secondary, group[1]))

    def margin(index):
        p_units = np.array([unit(primary, g[0]) for g in groups])
        s_units = np.array([unit(secondary, g[1]) for g in groups])
        matrix = p_units @ s_units.T
        crossing = np.concatenate(
            [np.delete(matrix[index], index), np.delete(matrix[:, index], index)]
        )
        return float(matrix[index, index]) - float(crossing.max(initial=-1.0))

    whole = [list(range(len(primary))), list(range(len(secondary)))]
    candidates = align_embeddings(
        primary,
        secondary,
        source_lengths=list(map(len, p_texts)),
        target_lengths=list(map(len, s_texts)),
        minimum_confidence=0.3,
        sentence_groups=True,
    )
    groups, p_cursor, s_cursor = [], 0, 0
    for candidate in candidates:
        p_indexes = list(range(p_cursor, candidate.source_indices[-1] + 1))
        s_indexes = list(range(s_cursor, candidate.target_indices[-1] + 1))
        groups.append([p_indexes, s_indexes])
        p_cursor, s_cursor = p_indexes[-1] + 1, s_indexes[-1] + 1
    if not groups:
        return [(*whole, similarity(whole), None)]
    groups[-1][0].extend(range(p_cursor, len(primary)))
    groups[-1][1].extend(range(s_cursor, len(secondary)))
    while len(groups) > 1:
        scores = [(similarity(g), margin(i)) for i, g in enumerate(groups)]
        worst = min(
            range(len(groups)),
            key=lambda i: min(
                scores[i][0] - CHUNK_MINIMUM_SIMILARITY, scores[i][1] - CHUNK_MINIMUM_MARGIN
            ),
        )
        if (
            scores[worst][0] >= CHUNK_MINIMUM_SIMILARITY
            and scores[worst][1] >= CHUNK_MINIMUM_MARGIN
        ):
            break
        options = []
        for neighbour in (worst - 1, worst + 1):
            if 0 <= neighbour < len(groups):
                a, b = sorted((worst, neighbour))
                merged = [groups[a][0] + groups[b][0], groups[a][1] + groups[b][1]]
                options.append((similarity(merged), a, b, merged))
        _, a, b, merged = max(options)
        groups[a : b + 1] = [merged]
    if len(groups) == 1:
        return [(*groups[0], similarity(groups[0]), None)]
    return [(g[0], g[1], similarity(g), margin(i)) for i, g in enumerate(groups)]


def test_within_a_sentence_the_window_merges_exactly_as_the_full_recount_did():
    import numpy as np

    from almonium_book_processor.processing.sentence_correspondence import _refine

    rng = np.random.default_rng(7)
    for _ in range(40):
        n, m = rng.integers(2, 8, size=2)
        meaning = rng.normal(size=(max(n, m), 16))
        primary = meaning[:n] + rng.normal(scale=rng.uniform(0.2, 2.0), size=(n, 16))
        secondary = meaning[:m] + rng.normal(scale=rng.uniform(0.2, 2.0), size=(m, 16))
        texts = ["x" * int(k) for k in rng.integers(5, 60, size=max(n, m))]
        got = _refine(primary, secondary, texts[:n], texts[:m])
        want = _refine_as_it_was(primary, secondary, texts[:n], texts[:m])
        assert [(g[0], g[1]) for g in got] == [(g[0], g[1]) for g in want]
        for a, b in zip(got, want, strict=True):
            assert a[2] == pytest.approx(b[2], abs=1e-9)
            assert (a[3] is None) == (b[3] is None)
            assert a[3] is None or a[3] == pytest.approx(b[3], abs=1e-9)


def test_a_page_long_paragraph_refines_in_seconds():
    import time

    import numpy as np

    from almonium_book_processor.processing.sentence_correspondence import _refine

    rng = np.random.default_rng(1)
    meaning = rng.normal(size=(250, 64))
    primary = meaning + rng.normal(scale=3.0, size=(250, 64))
    secondary = meaning + rng.normal(scale=3.0, size=(250, 64))
    started = time.perf_counter()
    _refine(primary, secondary, ["x" * 30] * 250, ["y" * 30] * 250)
    assert time.perf_counter() - started < 10


def test_the_precomputed_window_table_aligns_exactly_as_the_cell_by_cell_cosines(monkeypatch):
    import numpy as np

    from almonium_book_processor.processing import nlp

    rng = np.random.default_rng(11)
    cases = []
    for _ in range(30):
        n, m = rng.integers(1, 12, size=2)
        meaning = rng.normal(size=(max(n, m), 12))
        source = (meaning[:n] + rng.normal(scale=1.0, size=(n, 12))).tolist()
        target = (meaning[:m] + rng.normal(scale=1.0, size=(m, 12))).tolist()
        lengths = (rng.integers(5, 80, size=n).tolist(), rng.integers(5, 80, size=m).tolist())
        cases.append((source, target, lengths, bool(rng.integers(0, 2))))

    def run():
        return [
            [
                (c.source_indices, c.target_indices, round(c.confidence, 9))
                for c in nlp.align_embeddings(
                    source,
                    target,
                    source_lengths=lengths[0] if with_lengths else None,
                    target_lengths=lengths[1] if with_lengths else None,
                    minimum_confidence=0.3,
                    sentence_groups=True,
                )
            ]
            for source, target, lengths, with_lengths in cases
        ]

    fast = run()
    monkeypatch.setattr(
        nlp,
        "_confidence_table",
        lambda source, target, sl, tl: (
            lambda si, ti: nlp._alignment_confidence(source, target, sl, tl, si, ti)
        ),
    )
    assert fast == run()


def test_a_long_region_is_not_merged_away_by_a_phrase_repeated_far_off():
    import numpy as np

    from almonium_book_processor.processing.sentence_correspondence import _refine

    # Twenty clauses, each matching its own partner; clause 15 repeats clause 0 word for
    # word ("sagte K."). Against the whole region clause 0 has a perfect rival and would
    # merge; only its neighbours compete with it now.
    rng = np.random.default_rng(3)
    meaning = rng.normal(size=(20, 32))
    meaning[15] = meaning[0]
    primary = meaning + rng.normal(scale=0.2, size=meaning.shape)
    secondary = meaning + rng.normal(scale=0.2, size=meaning.shape)
    texts = ["x" * 40] * 20
    groups = _refine(primary, secondary, texts, texts)
    assert [(g[0], g[1]) for g in groups] == [([i], [i]) for i in range(20)]


def test_a_paragraph_of_a_hundred_sentences_is_aligned_sentence_by_sentence():
    from almonium_book_processor.processing.sentence_correspondence import correspond

    def block(word, count):
        text = " ".join(f"{word} {i}." for i in range(count))
        spans, cursor = [], 0
        for i in range(count):
            piece = f"{word} {i}."
            start = text.index(piece, cursor)
            spans.append({"start": start, "end": start + len(piece)})
            cursor = start + len(piece)
        return SimpleNamespace(text=text, sentences=spans)

    p, s = block("Eins", 100), block("One", 100)

    def embed(texts, **_):
        vectors = []
        for text in texts:
            vector = [0.0] * 100
            vector[int(text.split()[1].rstrip("."))] = 1.0
            vectors.append(vector)
        return vectors

    with patch(
        "almonium_book_processor.processing.sentence_correspondence.embed_texts",
        side_effect=embed,
    ):
        result = correspond(p, s)
    assert result["method"] == "offline_embeddings"
    assert len(result["groups"]) == 100
    assert all(g["certain"] and g["primary"] == g["secondary"] for g in result["groups"])


def test_a_text_read_from_the_worker_cache_outlives_ones_never_read_again(settings):
    settings.NLP_EMBEDDING_CACHE_TEXTS = 3
    with patch(
        "almonium_book_processor.processing.sentence_correspondence.embed_texts",
        side_effect=lambda texts, **_: [[1.0, float(i)] for i, _ in enumerate(texts)],
    ):
        sentence_correspondence.prefetch(["original", "first companion", "spare"])
        sentence_correspondence._embed(["original"], None, {})  # read: the youngest now
        sentence_correspondence.prefetch(["second companion"])
    texts = [key[-1] for key in sentence_correspondence._vectors]
    assert texts == ["spare", "original", "second companion"]


def test_long_texts_pool_their_pieces_as_the_text_by_text_loop_did(monkeypatch):
    import math

    import numpy as np

    from almonium_book_processor.processing import nlp

    class Tokenizer:
        def __call__(self, text, **kwargs):
            if isinstance(text, list):
                return {"input_ids": [[0, *item, 0] for item in text]}
            return {"input_ids": [0, *text, 0]}

        def num_special_tokens_to_add(self):
            return 2

    rng = np.random.default_rng(9)

    class Model:
        tokenizer = Tokenizer()
        max_seq_length = 12

        def encode(self, texts, **kwargs):
            self.texts = list(texts)
            return rng.normal(size=(len(texts), 6)).astype(np.float32)

    model = Model()
    monkeypatch.setattr(nlp, "_embedding_model", lambda _: model)
    texts = ["short", "a much longer text that must be split", "mid sized one", "x" * 30]
    pooled = nlp.embed_texts(texts, chunk_long=True)

    # The reference: each text's pieces found by scanning every piece, summed in Python.
    owners, weights = [], []
    for owner, text in enumerate(texts):

        def leaves(piece):
            if len(piece) + 2 <= model.max_seq_length:
                return [piece]
            middle = len(piece) // 2
            spaces = [
                i
                for i, c in enumerate(piece)
                if c.isspace() and len(piece) // 4 <= i <= 3 * len(piece) // 4
            ]
            split = min(spaces, key=lambda i: abs(i - middle)) + 1 if spaces else middle
            return leaves(piece[:split]) + leaves(piece[split:])

        for leaf in leaves(text):
            owners.append(owner)
            weights.append(max(1, len(leaf)))
    # The fake model's vectors again: the same seed, the same single draw.
    encoded = np.random.default_rng(9).normal(size=(len(owners), 6)).astype(np.float32)
    assert len(model.texts) == len(owners)
    for owner in range(len(texts)):
        parts = [(v, w) for v, w, o in zip(encoded, weights, owners, strict=True) if o == owner]
        mean = [sum(float(v[d]) * w for v, w in parts) for d in range(6)]
        norm = math.sqrt(sum(v * v for v in mean))
        assert pooled[owner] == pytest.approx([v / norm for v in mean], abs=1e-12)
