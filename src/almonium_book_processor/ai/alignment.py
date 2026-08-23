from __future__ import annotations

import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class AlignmentDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_block_ids: list[str] = Field(min_length=1)
    target_block_ids: list[str] = Field(min_length=1)
    relation: Literal["1:1", "1:n", "n:1", "n:m"]
    confidence: float = Field(ge=0, le=1)
    evidence: str

    @model_validator(mode="after")
    def relation_matches_cardinality(self) -> AlignmentDecision:
        source_many = len(self.source_block_ids) > 1
        target_many = len(self.target_block_ids) > 1
        if source_many and target_many:
            expected = "n:m"
        elif source_many:
            expected = "n:1"
        elif target_many:
            expected = "1:n"
        else:
            expected = "1:1"
        if self.relation != expected:
            raise ValueError("relation must match source and target block cardinality")
        return self


class ChapterAdjudication(BaseModel):
    model_config = ConfigDict(extra="forbid")

    same_text: bool
    confidence: float = Field(ge=0, le=1)
    alignments: list[AlignmentDecision]
    unmatched_source_block_ids: list[str]
    unmatched_target_block_ids: list[str]
    needs_human_review: bool
    notes: str

    @model_validator(mode="after")
    def block_ids_are_not_reused(self) -> ChapterAdjudication:
        source_ids = [item for row in self.alignments for item in row.source_block_ids]
        target_ids = [item for row in self.alignments for item in row.target_block_ids]
        if len(source_ids) != len(set(source_ids)):
            raise ValueError("A source block may appear in at most one alignment group")
        if len(target_ids) != len(set(target_ids)):
            raise ValueError("A target block may appear in at most one alignment group")
        if len(self.unmatched_source_block_ids) != len(set(self.unmatched_source_block_ids)):
            raise ValueError("An unmatched source block may appear at most once")
        if len(self.unmatched_target_block_ids) != len(set(self.unmatched_target_block_ids)):
            raise ValueError("An unmatched target block may appear at most once")
        if set(source_ids) & set(self.unmatched_source_block_ids):
            raise ValueError("A source block cannot be both aligned and unmatched")
        if set(target_ids) & set(self.unmatched_target_block_ids):
            raise ValueError("A target block cannot be both aligned and unmatched")
        return self


ALIGNMENT_OUTPUT_SCHEMA = ChapterAdjudication.model_json_schema()

ALIGNMENT_SYSTEM_PROMPT = """You align two editions of the same literary work across languages.
Chapter numbering and boundaries may differ: one chapter can be split, merged, omitted, or added.
Match passages by meaning and narrative content, not by position, spelling, names alone, or chapter
numbers. Preserve monotonic reading order. A block may occur in at most one group. Use 1:n or n:1
when paragraph boundaries differ. Exclude headings or other blocks only when they have no meaningful
counterpart. Mark needs_human_review when the editions are not the same underlying passage, order is
ambiguous, content is abridged beyond reliable matching, or confidence is below 0.80. Return only
the required structured result."""

ALIGNMENT_USER_TEMPLATE = """Adjudicate this source/target chapter window.

Source language: {source_language}
Target language: {target_language}
Source chapters: {source_chapters}
Target chapters: {target_chapters}

SOURCE BLOCKS
{source_blocks}

TARGET BLOCKS
{target_blocks}

LOCAL EMBEDDING CANDIDATES (hints only; correct them when necessary)
{local_candidates}
"""


def render_block(block) -> str:
    return json.dumps(
        {
            "id": str(block.id),
            "stable_id": block.block_id,
            "chapter": block.chapter.sequence,
            "type": block.block_type,
            "text": block.text,
        },
        ensure_ascii=False,
    )
