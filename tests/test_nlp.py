import pytest

from almonium_book_processor.processing.nlp import aggregate_embeddings, align_embeddings


def test_alignment_is_monotonic_and_filters_low_confidence() -> None:
    candidates = align_embeddings(
        source=[[1.0, 0.0], [0.0, 1.0], [-1.0, 0.0]],
        target=[[0.9, 0.1], [0.1, 0.9], [1.0, 0.0]],
        minimum_confidence=0.8,
    )

    assert [(item.source_index, item.target_index) for item in candidates] == [(0, 0), (1, 1)]


def test_alignment_requires_consistent_dimensions() -> None:
    with pytest.raises(ValueError, match="same dimensions"):
        align_embeddings([[1.0, 0.0]], [[1.0]])


def test_alignment_supports_one_to_many_and_many_to_one_groups() -> None:
    one_to_many = align_embeddings(
        source=[[1.0, 0.0]],
        target=[[1.0, 0.0], [1.0, 0.0]],
    )
    many_to_one = align_embeddings(
        source=[[1.0, 0.0], [1.0, 0.0]],
        target=[[1.0, 0.0]],
    )

    assert [(item.source_indices, item.target_indices) for item in one_to_many] == [((0,), (0, 1))]
    assert [(item.source_indices, item.target_indices) for item in many_to_one] == [((0, 1), (0,))]


def test_alignment_validates_optional_length_inputs() -> None:
    with pytest.raises(ValueError, match="source_lengths"):
        align_embeddings(
            source=[[1.0, 0.0]],
            target=[[1.0, 0.0]],
            source_lengths=[],
        )


def test_aggregate_embeddings_normalizes_chapter_means() -> None:
    aggregates = aggregate_embeddings(
        [[1.0, 0.0], [0.0, 1.0], [-1.0, 0.0]],
        [[0, 1], [2]],
    )

    assert aggregates[0] == pytest.approx([2**-0.5, 2**-0.5])
    assert aggregates[1] == pytest.approx([-1.0, 0.0])


def test_chapter_level_alignment_can_absorb_a_split_boundary() -> None:
    source_chapters = [[1.0, 0.0], [0.0, 1.0], [-1.0, 0.0]]
    target_chapters = [[2**-0.5, 2**-0.5], [-1.0, 0.0]]

    candidates = align_embeddings(
        source_chapters,
        target_chapters,
        minimum_confidence=0.4,
    )

    assert [(item.source_indices, item.target_indices) for item in candidates] == [
        ((0, 1), (0,)),
        ((2,), (1,)),
    ]
