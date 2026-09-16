"""Bounded offline correspondence within an already aligned paragraph pair."""

from almonium_book_processor.processing.nlp import _cosine, align_embeddings, embed_texts

VERSION = "offline-sentence-v3"


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


def correspond(primary, secondary):
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
        vectors = embed_texts(left + right, chunk_long=True)
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
