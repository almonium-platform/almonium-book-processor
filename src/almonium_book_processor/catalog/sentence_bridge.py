"""Sentence groups for two editions that were each aligned with their original, not with each other.

A level adaptation and a translation are both made from the original, paragraph for
paragraph, and each is sentence-aligned with it (catalog/sentence_alignment_queue.py). Read
beside one another they share no alignment of their own. Their two alignments meet on the
original's clauses, though: whatever of the adaptation and of the translation is tied to the
same stretch of the original says the same thing. Joining them there costs nothing: no
embedding, no model call, and nothing to keep current beyond the two alignments it reads.

Aligning such a pair directly is the harder task (a rewording and a translation at once) and
measured worse: on 360 rewritten paragraphs of six pairs the offline aligner confirmed 62% of
the adapted words directly and 74% joined through the original, 96.5% once the join reads the
model's readings of the two alignments, which are already paid for
(docs/SENTENCE_ALIGNMENT.md).

A joined group is as coarse as the coarser of the two alignments where it lies: a B1 edition
that cuts one sentence of the original in three is matched three sentences to the
translation's one. It is confirmed only when everything it was joined from was.
"""

from __future__ import annotations

VERSION = "sentence-bridge-v1"
ACCEPTANCE = "bridged"


def _order(group: dict) -> tuple:
    return (
        min(group["primary"], default=float("inf")),
        min(group["secondary"], default=float("inf")),
    )


def bridge(first: dict, second: dict, origin, primary, secondary) -> dict | None:
    """``primary`` and ``secondary``'s sentence groups, joined on the block both were made from.

    ``first`` is the alignment of ``origin`` with ``primary`` and ``second`` that of ``origin``
    with ``secondary``, each as the reader is served it and with the original on its primary
    side. None when either has no groups: there is nothing to join.
    """

    if not first.get("groups") or not second.get("groups"):
        return None
    spans = {
        "primary": first.get("secondary_spans", primary.sentences),
        "secondary": second.get("secondary_spans", secondary.sentences),
    }
    parent: dict[tuple, tuple] = {}

    def find(node):
        parent.setdefault(node, node)
        while parent[node] != node:
            parent[node] = parent[parent[node]]
            node = parent[node]
        return node

    def union(left, right):
        left, right = find(left), find(right)
        if left != right:
            parent[right] = left

    # The original as each alignment cut it. Clause cuts depend on the block alone, so the
    # two usually agree span for span; where one alignment went by sentence and the other
    # by clause, every piece of the original belongs with the pieces it shares text with.
    ours = first.get("primary_spans", origin.sentences)
    theirs = second.get("primary_spans", origin.sentences)
    i = j = 0
    while i < len(ours) and j < len(theirs):
        if ours[i]["start"] < theirs[j]["end"] and theirs[j]["start"] < ours[i]["end"]:
            union(("origin", 0, i), ("origin", 1, j))
        if ours[i]["end"] <= theirs[j]["end"]:
            i += 1
        else:
            j += 1

    doubted, clauses = [], []
    for view, (data, side) in enumerate(((first, "primary"), (second, "secondary"))):
        for group in data["groups"]:
            nodes = [("origin", view, index) for index in group["primary"]]
            nodes += [(side, index) for index in group["secondary"]]
            if not nodes:
                continue
            for node in nodes[1:]:
                union(nodes[0], node)
            if not group.get("certain"):
                doubted.append(nodes[0])
            if group.get("granularity") == "clause":
                clauses.append(nodes[0])

    groups: dict[tuple, dict] = {}
    for side in ("primary", "secondary"):
        for index in range(len(spans[side])):
            group = groups.setdefault(find((side, index)), {"primary": [], "secondary": []})
            group[side].append(index)
    doubted = {find(node) for node in doubted}
    clauses = {find(node) for node in clauses}
    for root, group in groups.items():
        # What the original ties to one side only has no counterpart to be confirmed against.
        group["certain"] = bool(group["primary"] and group["secondary"]) and root not in doubted
        group["acceptance"] = ACCEPTANCE
        group["granularity"] = "clause" if root in clauses else "sentence"
    return {
        "groups": sorted(groups.values(), key=_order),
        "primary_spans": spans["primary"],
        "secondary_spans": spans["secondary"],
        "method": ACCEPTANCE,
        "segmentation": next(
            (data["segmentation"] for data in (first, second) if data.get("segmentation")),
            "sentences",
        ),
    }
