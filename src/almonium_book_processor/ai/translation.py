"""Structured literary translation of a canonical edition, block for block.

Translation is the project's alignment backbone. The model must return exactly
one output block per input block, echoing the stable block id, so the resulting
edition inherits the canonical ``align_group`` of its source and needs no
inferred alignment pass at all.
"""

from __future__ import annotations

import json

from pydantic import BaseModel, ConfigDict, Field, model_validator

TRANSLATION_SCHEMA_VERSION = 1


class TranslatedBlock(BaseModel):
    model_config = ConfigDict(extra="forbid")

    block_id: str = Field(min_length=1)
    text: str
    sentence_count_changed: bool
    confidence: float = Field(ge=0, le=1)
    note: str


class ChapterTranslation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    blocks: list[TranslatedBlock]

    @model_validator(mode="after")
    def block_ids_are_unique(self) -> ChapterTranslation:
        ids = [block.block_id for block in self.blocks]
        if len(ids) != len(set(ids)):
            raise ValueError("A block_id may appear at most once in a translated chapter")
        return self


TRANSLATION_OUTPUT_SCHEMA = ChapterTranslation.model_json_schema()

TRANSLATION_SYSTEM_PROMPT = """You are a literary translator working from {source_language_name} \
into {target_language_name}.
You are translating "{work_title}" by {author}{year_clause}.

Your translation will be displayed beside the original for language learners, paragraph by
paragraph. Structural fidelity therefore matters as much as fluency.

REGISTER
- Target register: {register}.
- Preserve the author's sentence rhythm. Where the original uses long subordinated periods, do not
  break them into short sentences.
- Preserve dialogue voice: dialect, register shifts, and idiosyncratic speech must survive.
- Use {target_language_name} conventions for quotation marks and dashes.

STRUCTURAL RULES - these are absolute
- Return exactly one output block for every input block, in the same order.
- Never merge two input blocks. Never split one input block into two.
- Echo the block_id exactly as it was given to you.
- Preserve sentence count within a block wherever {target_language_name} permits. If you must
  deviate, deviate by at most one sentence and set "sentence_count_changed": true for that block.
- Never add explanatory content, translator's notes, or clarifying phrases that are not in the
  source. Do not elaborate an image the author left plain.
- Never omit a clause because it is difficult.
- Leave proper nouns untranslated unless {target_language_name} has an established conventional
  form.
- Preserve emphasis markers exactly as they appear.
- A block whose type is "heading" is a heading: translate it as a heading and do not expand it.
- Set "confidence" below 0.7 and explain the difficulty in "note" only when a block was genuinely
  hard; otherwise leave "note" empty.

Return only the required structured result."""

TRANSLATION_USER_TEMPLATE = """Translate this chapter.

Chapter: {chapter_sequence}{chapter_title_clause}
Source language: {source_language}
Target language: {target_language}

SOURCE BLOCKS
{source_blocks}
"""


def render_source_block(block) -> str:
    return json.dumps(
        {
            "block_id": block.block_id,
            "type": block.block_type,
            "text": block.text,
        },
        ensure_ascii=False,
    )
