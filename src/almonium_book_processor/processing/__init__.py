"""Offline text-processing primitives used by book workers."""

from almonium_book_processor.processing.nlp import (
    AlignmentCandidate,
    align_embeddings,
    embed_texts,
    split_sentences,
)

__all__ = ["AlignmentCandidate", "align_embeddings", "embed_texts", "split_sentences"]
