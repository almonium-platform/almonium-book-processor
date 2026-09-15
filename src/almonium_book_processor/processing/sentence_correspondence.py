"""Bounded offline correspondence within an already aligned paragraph pair."""

from almonium_book_processor.processing.nlp import align_embeddings, embed_texts

VERSION = "offline-sentence-v2"


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
        return {"groups": [], "method": "paragraph_fallback"}
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
    if max(len(left), len(right)) > 80 or max(map(len, left + right)) > 1200:
        return {"groups": [], "method": "paragraph_fallback"}
    try:
        vectors = embed_texts(left + right, reject_truncation=True)
    except ValueError as error:
        if str(error) != "Sentence exceeds embedding token limit":
            raise
        return {"groups": [], "method": "paragraph_fallback"}
    candidates = align_embeddings(
        vectors[: len(left)],
        vectors[len(left) :],
        source_lengths=list(map(len, left)),
        target_lengths=list(map(len, right)),
        minimum_confidence=0.65,
        sentence_groups=True,
    )
    groups = [
        {
            "primary": list(c.source_indices),
            "secondary": list(c.target_indices),
            # Similarity is a heuristic, not calibrated accuracy or editorial certification.
            "certain": c.confidence >= 0.82,
            "similarity": round(c.confidence, 4),
        }
        for c in candidates
    ]
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
    return {"groups": groups, "method": "offline_embeddings", "highlight_threshold": 0.82}
