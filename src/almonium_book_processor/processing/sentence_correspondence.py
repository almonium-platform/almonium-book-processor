"""Bounded offline correspondence within an already aligned paragraph pair."""

import re
from types import SimpleNamespace

from almonium_book_processor.processing.nlp import _cosine, align_embeddings, embed_texts

VERSION = "offline-sentence-v7"


def _cover_groups(primary_count, secondary_count, groups):
    """Give every sentence a partner while retaining the embedding matches.

    The paragraph pair is already exact. An uncertain sentence correspondence is
    still useful for reading, provided it is kept marked as uncertain in the
    artifact. Positional groups fill only the intervals embeddings left open.
    """
    anchors = sorted(
        (g for g in groups if g["primary"] and g["secondary"]),
        key=lambda g: (g["primary"][0], g["secondary"][0]),
    )
    result = []
    p_cursor = s_cursor = 0

    def gap(p_end, s_end):
        nonlocal p_cursor, s_cursor
        primary = list(range(p_cursor, p_end))
        secondary = list(range(s_cursor, s_end))
        if primary and secondary:
            count = min(len(primary), len(secondary))
            for index in range(count):
                p_slice = primary[
                    index * len(primary) // count : (index + 1) * len(primary) // count
                ]
                s_slice = secondary[
                    index * len(secondary) // count : (index + 1) * len(secondary) // count
                ]
                result.append(
                    {
                        "primary": p_slice,
                        "secondary": s_slice,
                        "certain": False,
                        "acceptance": "positional_fallback",
                    }
                )
        elif primary or secondary:
            if result:
                result[-1]["primary"] = [*result[-1]["primary"], *primary]
                result[-1]["secondary"] = [*result[-1]["secondary"], *secondary]
                result[-1]["certain"] = False
            elif anchors:
                anchors[0].update(
                    primary=[*primary, *anchors[0]["primary"]],
                    secondary=[*secondary, *anchors[0]["secondary"]],
                    certain=False,
                )
        p_cursor, s_cursor = p_end, s_end

    for anchor in anchors:
        gap(anchor["primary"][0], anchor["secondary"][0])
        result.append(anchor)
        p_cursor = anchor["primary"][-1] + 1
        s_cursor = anchor["secondary"][-1] + 1
    gap(primary_count, secondary_count)
    return result


def sentence_texts(block):
    cursor = 0
    result = []
    for span in block.sentences:
        start, end = span.get("start"), span.get("end")
        if (
            not isinstance(start, int)
            or not isinstance(end, int)
            or not cursor <= start < end <= len(block.text)
        ):
            raise ValueError("Invalid sentence offsets; rerun sentence splitting")
        if block.text[cursor:start].strip():
            raise ValueError("Sentence offsets omit text; rerun sentence splitting")
        result.append(block.text[start:end])
        cursor = end
    if block.text[cursor:].strip():
        raise ValueError("Sentence offsets omit text; rerun sentence splitting")
    return result


def _correspond(primary, secondary, model_name=None):
    left, right = sentence_texts(primary), sentence_texts(secondary)
    if not left or not right:
        return {
            "groups": [],
            "method": "paragraph_fallback",
            "fallback_reason": "missing_sentences",
        }
    if primary.text == secondary.text and primary.sentences == secondary.sentences:
        return {
            "method": "identical_text",
            "groups": [
                {"primary": [i], "secondary": [i], "certain": True} for i in range(len(left))
            ],
        }
    if len(left) == len(right) == 1:
        return {
            "method": "inherited_single_sentence",
            "groups": [{"primary": [0], "secondary": [0], "certain": True}],
        }
    # Bound CPU and avoid quietly feeding oversized sentences to a truncating encoder.
    if max(len(left), len(right)) > 80 or max(map(len, left + right)) > 12000:
        return {"groups": [], "method": "paragraph_fallback", "fallback_reason": "size_limit"}
    try:
        vectors = embed_texts(left + right, chunk_long=True, model_name=model_name)
    except ValueError as error:
        if str(error) != "Sentence exceeds embedding token limit":
            raise
        return {"groups": [], "method": "paragraph_fallback", "fallback_reason": "token_limit"}
    candidates = align_embeddings(
        vectors[: len(left)],
        vectors[len(left) :],
        source_lengths=list(map(len, left)),
        target_lengths=list(map(len, right)),
        minimum_confidence=0.65,
        sentence_groups=True,
    )
    groups = []
    similarities = [[_cosine(a, b) for b in vectors[len(left) :]] for a in vectors[: len(left)]]
    for c in candidates:
        margin = None
        # Lower-score acceptance is limited to distinct reciprocal 1:1 matches.
        # Split/merged groups keep the existing stricter acceptance rule.
        if len(c.source_indices) == len(c.target_indices) == 1:
            i, j = c.source_indices[0], c.target_indices[0]
            competitors = [similarities[i][k] for k in range(len(right)) if k != j]
            competitors += [similarities[k][j] for k in range(len(left)) if k != i]
            margin = similarities[i][j] - max(competitors, default=1.0)
        relative = c.confidence >= 0.75 and margin is not None and margin >= 0.10
        certain = c.confidence >= 0.82 or relative
        groups.append(
            {
                "primary": list(c.source_indices),
                "secondary": list(c.target_indices),
                "certain": certain,
                "similarity": round(c.confidence, 4),
                "margin": round(margin, 4) if margin is not None else None,
                "acceptance": "absolute"
                if c.confidence >= 0.82
                else "reciprocal_margin"
                if relative
                else "uncertain",
            }
        )
    for side, texts in (("primary", left), ("secondary", right)):
        used = {i for group in groups for i in group[side]}
        for i in range(len(texts)):
            if i not in used:
                groups.append(
                    {
                        "primary": [i] if side == "primary" else [],
                        "secondary": [i] if side == "secondary" else [],
                        "certain": False,
                    }
                )
    return {
        "groups": groups,
        "method": "offline_embeddings",
        "highlight_threshold": 0.82,
        "relative_minimum": 0.75,
        "reciprocal_margin": 0.10,
    }


def clause_spans(block):
    """Refine sentence spans at semicolons, preserving text and Unicode offsets."""
    sentence_texts(block)  # Validate the original segmentation first.
    result = []
    for sentence in block.sentences:
        start, end = sentence["start"], sentence["end"]
        cursor = start
        for match in re.finditer(r";\s+", block.text[start:end]):
            boundary = start + match.start() + 1
            # Do not create fragments out of punctuation or list labels.
            if len(re.findall(r"\w+", block.text[cursor:boundary])) < 2:
                continue
            if len(re.findall(r"\w+", block.text[start + match.end() : end])) < 2:
                continue
            result.append({"start": cursor, "end": boundary})
            cursor = start + match.end()
        result.append({"start": cursor, "end": end})
    return result


def correspond(primary, secondary, model_name=None):
    coarse = _correspond(primary, secondary, model_name)
    left, right = clause_spans(primary), clause_spans(secondary)
    if len(left) == len(primary.sentences) and len(right) == len(secondary.sentences):
        coarse["groups"] = _cover_groups(len(left), len(right), coarse["groups"])
        return coarse
    groups = []
    # Refine accepted parents when at least two useful fine matches survive.
    # Uncertain clauses stay visible but unhighlighted within the paired paragraph.
    for parent in coarse["groups"]:
        indexes = {}
        blocks = {}
        for side, block, spans in (("primary", primary, left), ("secondary", secondary, right)):
            indexes[side] = [
                i
                for i, span in enumerate(spans)
                if any(
                    block.sentences[j]["start"]
                    <= span["start"]
                    < span["end"]
                    <= block.sentences[j]["end"]
                    for j in parent[side]
                )
            ]
            chosen = [spans[i] for i in indexes[side]]
            if chosen:
                start, end = chosen[0]["start"], chosen[-1]["end"]
                blocks[side] = SimpleNamespace(
                    text=block.text[start:end],
                    sentences=[
                        {"start": s["start"] - start, "end": s["end"] - start} for s in chosen
                    ],
                )
        split = any(len(indexes[side]) > len(parent[side]) for side in indexes)
        finer = None
        if parent["certain"] and split and len(blocks) == 2:
            candidate = _correspond(blocks["primary"], blocks["secondary"], model_name)
            if sum(
                bool(g["certain"] and g["primary"] and g["secondary"]) for g in candidate["groups"]
            ) >= 2 and all(g["primary"] and g["secondary"] for g in candidate["groups"]):
                finer = candidate["groups"]
        if finer:
            groups.extend(
                {
                    **g,
                    "granularity": "clause",
                    **{side: [indexes[side][i] for i in g[side]] for side in indexes},
                }
                for g in finer
            )
        else:
            groups.append({**parent, **indexes, "granularity": "sentence"})
    return {
        **coarse,
        "groups": _cover_groups(len(left), len(right), groups),
        "primary_spans": left,
        "secondary_spans": right,
        "segmentation": "semicolon-clauses-v2",
    }
