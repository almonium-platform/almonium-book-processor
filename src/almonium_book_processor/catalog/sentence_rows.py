"""The sentence alignment page's rows: each sentence group on one line, its two sides abreast.

A block pair becomes a run of rows, one per sentence group, so a sentence and its
counterpart always sit side by side and nobody has to click to find one. A group the
model matched carries its similarity; below ``LOW`` the page marks it for a look. A block
the aligner could not split (or that no job has aligned yet) is one paragraph row, and a
heading is always one row set as a heading.
"""

from __future__ import annotations

from datetime import datetime

from almonium_book_processor.catalog.titles import display_title

LOW = 0.75


def _sentences(text: str, spans: list[dict], indices: list[int]) -> str:
    return " ".join(text[spans[i]["start"] : spans[i]["end"]].strip() for i in indices)


def _order(group: dict) -> tuple:
    return (
        min(group["primary"], default=float("inf")),
        min(group["secondary"], default=float("inf")),
    )


def block_rows(block: dict, primary, secondary) -> dict:
    groups = block.get("sentence_alignment") or []
    heading = block.get("block_type") == "heading"
    row = {
        "primary_block_id": block["primary_block_id"],
        "secondary_block_id": block["secondary_block_id"],
        "heading": heading,
        "aligned": bool(block.get("alignment_provenance")),
        "groups": [],
    }
    if heading or not groups:
        row["groups"].append(
            {
                "number": 1 if heading else None,
                "primary": display_title(block["primary_text"], primary)
                if heading
                else block["primary_text"],
                "secondary": display_title(block["secondary_text"], secondary)
                if heading
                else block["secondary_text"],
                "confidence": None,
                "low": False,
                "paragraph": not heading,
            }
        )
        return row
    for number, group in enumerate(sorted(groups, key=_order), 1):
        similarity = group.get("similarity")
        row["groups"].append(
            {
                "number": number,
                "primary": _sentences(
                    block["primary_text"], block["primary_sentences"], group["primary"]
                ),
                "secondary": _sentences(
                    block["secondary_text"], block["secondary_sentences"], group["secondary"]
                ),
                "confidence": round(similarity * 100) if similarity is not None else None,
                "low": similarity is not None and similarity < LOW,
                "positional": group.get("acceptance") == "positional_fallback",
                "unmatched": not group["primary"] or not group["secondary"],
                "paragraph": False,
            }
        )
    return row


def chapter_rows(blocks: list[dict], primary, secondary) -> tuple[list[dict], dict]:
    rows = [block_rows(block, primary, secondary) for block in blocks]
    groups = [g for row in rows for g in row["groups"] if not row["heading"]]
    stamps = [
        b["alignment_provenance"]["created_at"]
        for b in blocks
        if b.get("alignment_provenance") and b["alignment_provenance"].get("created_at")
    ]
    stats = {
        "aligned": any(row["aligned"] for row in rows),
        "aligned_at": datetime.fromisoformat(max(stamps)) if stamps else None,
        "groups": sum(1 for g in groups if not g["paragraph"]),
        "low": sum(1 for g in groups if g["low"]),
    }
    return rows, stats


def short_model(model: str) -> str:
    """A local model as a person would name it: "MiniLM-L12 multilingual", "LaBSE"."""

    name = model.rsplit("/", 1)[-1]
    if "MiniLM-L12" in name:
        return "MiniLM-L12 multilingual" if "multilingual" in name else "MiniLM-L12"
    return name
