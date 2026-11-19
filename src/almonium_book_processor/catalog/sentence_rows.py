"""The sentence alignment page's rows: each sentence group on one line, its two sides abreast.

A block pair becomes a run of rows, one per sentence group, so a sentence and its
counterpart always sit side by side and nobody has to click to find one. A group the
model matched carries its similarity; one the aligner did not confirm (or, in an artifact
without that verdict, one below ``LOW``) the page marks for a look. A group joined through
the original (catalog/sentence_bridge.py) has no similarity of its own: it is confirmed when
everything it was joined from was. A block
the aligner could not split (or that no job has aligned yet) is one paragraph row, and a
heading is always one row set as a heading.
"""

from __future__ import annotations

from datetime import datetime

from almonium_book_processor.catalog.sentence_bridge import ACCEPTANCE as BRIDGED
from almonium_book_processor.catalog.titles import display_title

LOW = 0.75


def _sentences(text: str, spans: list[dict], indices: list[int]) -> str:
    return " ".join(text[spans[i]["start"] : spans[i]["end"]].strip() for i in indices)


def _order(group: dict) -> tuple:
    return (
        min(group["primary"], default=float("inf")),
        min(group["secondary"], default=float("inf")),
    )


# Paragraph view: a group's chunks share one of these tints on both sides. Six is
# enough for neighbours never to share one; numbering follows reading order.
TINTS = 6


def _pieces(text: str, spans: list[dict], owner: dict[int, dict]) -> list[dict]:
    """A side's text cut at its display spans, each span tagged with its group."""

    def tagged(piece_text, group):
        return {
            "text": piece_text,
            "group": group["number"] if group else None,
            "tint": (group["number"] - 1) % TINTS if group else None,
            "certain": bool(group and group["certain"]),
            "confidence": group["confidence"] if group else None,
            "adjudicated": bool(group and group.get("adjudicated")),
            "bridged": bool(group and group.get("bridged")),
        }

    pieces, cursor = [], 0
    for index, span in enumerate(spans):
        group = owner.get(index)
        if span["start"] > cursor:
            # The space inside one group carries its tint, so a group of several
            # chunks reads as one stretch, not as neighbours that share a colour.
            inside = group is not None and owner.get(index - 1) is group
            pieces.append(tagged(text[cursor : span["start"]], group if inside else None))
        pieces.append(tagged(text[span["start"] : span["end"]], group))
        cursor = span["end"]
    if cursor < len(text):
        pieces.append({"text": text[cursor:]})
    return pieces


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
    p_owner, s_owner = {}, {}
    for number, group in enumerate(sorted(groups, key=_order), 1):
        similarity = group.get("similarity")
        # A group a model read has no similarity; its verdict is the model's own.
        adjudicated = group.get("acceptance") == "llm_adjudication"
        bridged = group.get("acceptance") == BRIDGED
        tag = {
            "number": number,
            "certain": bool(group.get("certain")),
            "confidence": round(similarity * 100) if similarity is not None else None,
            "adjudicated": adjudicated,
            "bridged": bridged,
        }
        p_owner.update(dict.fromkeys(group["primary"], tag))
        s_owner.update(dict.fromkeys(group["secondary"], tag))
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
                # The aligner's own verdict decides: a confirmed clause pair often
                # scores under LOW, which was set for whole sentences.
                "low": (similarity is not None or adjudicated or bridged)
                and not group.get("certain", similarity is not None and similarity >= LOW),
                "adjudicated": adjudicated,
                "bridged": bridged,
                "positional": group.get("acceptance") == "positional_fallback",
                "unmatched": not group["primary"] or not group["secondary"],
                "paragraph": False,
                "clause": group.get("granularity") == "clause",
            }
        )
    row["primary_pieces"] = _pieces(block["primary_text"], block["primary_sentences"], p_owner)
    row["secondary_pieces"] = _pieces(
        block["secondary_text"], block["secondary_sentences"], s_owner
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
        "clauses": sum(1 for g in groups if g.get("clause")),
        "low": sum(1 for g in groups if g["low"]),
        "adjudicated": sum(1 for g in groups if g.get("adjudicated")),
        "bridged": sum(1 for g in groups if g.get("bridged")),
    }
    return rows, stats


def short_model(model: str) -> str:
    """A local model as a person would name it: "MiniLM-L12 multilingual", "LaBSE"."""

    name = model.rsplit("/", 1)[-1]
    if "MiniLM-L12" in name:
        return "MiniLM-L12 multilingual" if "multilingual" in name else "MiniLM-L12"
    return name
