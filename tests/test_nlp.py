import pytest

from almonium_book_processor.processing.nlp import align_embeddings


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
