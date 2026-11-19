"""Presentation-free inherited correspondence for generated edition families."""

import hashlib
import json

from django.conf import settings

from almonium_book_processor.catalog import sentence_bridge
from almonium_book_processor.catalog.models import Edition, EditionArtifact


def pair_hash(primary, secondary):
    # Include segmentation itself: changing the NLP version/boundaries cannot reuse spans.
    data = [
        [str(b.id), b.text, b.sentences, str(b.align_group), b.edition.language]
        for b in (primary, secondary)
    ]
    return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()


def canonical_root(edition):
    seen = set()
    while edition.source_edition_id:
        if edition.id in seen:
            raise ValueError("Cyclic edition lineage")
        seen.add(edition.id)
        edition = edition.source_edition
    return edition.id


def _blocks(edition, read):
    """An edition's blocks in reading order, read once per ``read`` where one is passed."""

    if read is not None and edition.id in read:
        return read[edition.id]
    blocks = list(
        edition.blocks.select_related("chapter", "edition").order_by(
            "chapter__sequence", "sequence"
        )
    )
    if read is not None:
        read[edition.id] = blocks
    return blocks


def inherited_pairs(edition, other, read=None):
    """The two editions' blocks paired through the groups both inherit; [] unless complete.

    A caller that pairs one edition with several others passes the same dictionary as
    ``read`` each time, so that every edition's blocks are read once.
    """

    if (
        edition.id == other.id
        or edition.work_id != other.work_id
        or not edition.supports_parallel_reading
        or not other.supports_parallel_reading
        or canonical_root(edition) != canonical_root(other)
    ):
        return []
    primary, secondary = _blocks(edition, read), _blocks(other, read)
    # This path promises complete 1:1 inherited groups, never guesses or drops a gap.
    # A block without text (a scene-break separator, a bare image) is never sent to
    # translation, so a parallel edition lacks it by design; it has nothing to read
    # beside anything and is the only kind of group allowed to be one-sided.
    left = {b.align_group: b for b in primary if b.align_group}
    right = {b.align_group: b for b in secondary if b.align_group}
    one_sided = [
        block
        for blocks, other in ((left, right), (right, left))
        for group, block in blocks.items()
        if group not in other
    ]
    if (
        not primary
        or len(left) != len(primary)
        or len(right) != len(secondary)
        or any(block.text.strip() for block in one_sided)
    ):
        return []
    return [(b, right[b.align_group]) for b in primary if b.align_group in right]


# How many pair hashes one query asks for: a long book has tens of thousands.
_DIGESTS_PER_QUERY = 5000


def served_alignments(editions, digests):
    """The sentence alignment the reader is served, by the pair hash it was made for.

    Of the current alignment artifacts stored under ``editions``, those made for
    ``digests``: an offline one, and where a model read its unconfirmed stretches, that
    reading in its place. An original holds the alignments of every edition made from it,
    so asking by hash reads one companion's share and not the whole family's.
    """

    from django.db.models import Q

    from almonium_book_processor.catalog import sentence_adjudication
    from almonium_book_processor.catalog.offline_sentence_alignment import (
        available_models,
        processor_version,
    )

    offline = [processor_version(model) for model in available_models()]
    digests = list(dict.fromkeys(digests))
    candidates = []
    for start in range(0, len(digests), _DIGESTS_PER_QUERY):
        candidates += EditionArtifact.objects.filter(
            Q(
                processor_version__in=[
                    *offline,
                    f"sentence-pair-v2:{settings.OPENAI_TRANSLATION_QUALITY_MODEL}",
                ]
            )
            | Q(processor_version__startswith=f"{sentence_adjudication.VERSION}:"),
            edition__in=editions,
            kind=EditionArtifact.Kind.SENTENCE_ALIGNMENT,
            is_current=True,
            input_hash__in=digests[start : start + _DIGESTS_PER_QUERY],
        )
    candidates.sort(key=lambda a: (a.created_at, a.id))

    def served(a):
        return {
            **a.payload,
            "provenance": {
                "artifact_id": str(a.id),
                "processor_version": a.processor_version,
                "model": a.payload.get("model", "Not recorded"),
                "created_at": a.created_at.isoformat(),
                "input_hash": a.input_hash,
                "pipeline_run_id": str(a.pipeline_run_id) if a.pipeline_run_id else None,
                "segmentation": a.payload.get("segmentation", "sentences"),
            },
        }

    adjudicated = [a for a in candidates if "adjudication" in a.payload]
    artifacts = {
        a.input_hash: served(a)
        for a in sorted(
            (a for a in candidates if "adjudication" not in a.payload),
            key=lambda a: a.processor_version in offline,
        )
    }
    # A model's reading of the unconfirmed stretches stands in for the offline artifact it
    # was made from, and for no other: a later offline version is read as it is until its
    # own stretches are judged. Prefer the most complete overlay for the same base.
    for a in sorted(
        adjudicated,
        key=lambda a: (a.payload["adjudication"]["stretches"], a.updated_at),
        reverse=True,
    ):
        base = artifacts.get(a.input_hash)
        if base and base["provenance"]["processor_version"] == a.payload["adjudication"]["base"]:
            artifacts[a.input_hash] = {
                **served(a),
                "provenance": {
                    **served(a)["provenance"],
                    "adjudicated_by": a.payload["adjudication"]["model"],
                },
            }
    return artifacts


def common_origin(edition, other):
    """The edition both were made from, when it is neither of them; None for any other pair."""

    root = canonical_root(edition)
    if root in (edition.id, other.id) or root != canonical_root(other):
        return None
    return Edition.objects.filter(pk=root).first()


def _bridge(origin, editions, pairs, own, rows):
    """Fill the pairs that have no sentence groups of their own with those joined through
    ``origin``, the edition both were made from (catalog/sentence_bridge.py)."""

    blocks = {block.align_group: block for block in origin.blocks.select_related("edition")}
    legs = {}
    for index, (p, s) in enumerate(pairs):
        block = blocks.get(p.align_group)
        if block is None or rows[index].get("groups"):
            continue
        legs[index] = (
            block,
            (pair_hash(block, p), pair_hash(p, block)),
            (pair_hash(block, s), pair_hash(s, block)),
        )
    artifacts = served_alignments(
        [origin, *editions],
        [digest for _, first, second in legs.values() for digest in (*first, *second)],
    )
    for index, (block, first, second) in legs.items():
        first, second = _oriented(artifacts, *first), _oriented(artifacts, *second)
        joined = sentence_bridge.bridge(first, second, block, *pairs[index])
        if joined is None:
            continue
        rows[index] = {
            **joined,
            "provenance": {
                "artifact_id": None,
                "processor_version": sentence_bridge.VERSION,
                "model": None,
                # As fresh as the alignment that changed last: either one moves the join.
                "created_at": max(
                    first["provenance"]["created_at"], second["provenance"]["created_at"]
                ),
                "input_hash": own[index][0],
                "pipeline_run_id": None,
                "segmentation": joined["segmentation"],
                "bridged_through": origin.slug,
                "legs": [first["provenance"], second["provenance"]],
            },
        }


def inherited_payload(edition, other):
    pairs = inherited_pairs(edition, other)
    if not pairs:
        return None
    own = [(pair_hash(p, s), pair_hash(s, p)) for p, s in pairs]
    artifacts = served_alignments([edition, other], [digest for both in own for digest in both])
    rows = [_oriented(artifacts, forward, backward) for forward, backward in own]
    # An adaptation and a translation, or two translations, were each aligned with the
    # original and not with one another: their sentences are joined through it. A pair
    # staff aligned directly keeps its own alignment wherever that has groups.
    origin = common_origin(edition, other)
    if origin is not None:
        _bridge(origin, [edition, other], pairs, own, rows)
    return {
        "schema_version": 2,
        "primary_edition": edition.slug,
        "secondary_edition": other.slug,
        "primary_language": edition.language,
        "secondary_language": other.language,
        "alignment_strategy": "inherited_groups",
        "blocks": [
            {
                "chapter": p.chapter.sequence,
                "chapter_title": p.chapter.title,
                "sequence": p.sequence,
                "block_type": p.block_type,
                "align_group": str(p.align_group),
                "primary_block_id": p.block_id,
                "secondary_block_id": s.block_id,
                "primary_text": p.text,
                "secondary_text": s.text,
                "primary_sentences": row.get("primary_spans", p.sentences),
                "secondary_sentences": row.get("secondary_spans", s.sentences),
                "alignment_provenance": row.get("provenance"),
                "revision": forward,
                "sentence_alignment": row.get("groups", []),
            }
            for (p, s), (forward, _), row in zip(pairs, own, rows, strict=True)
        ],
    }


def aligned_data(artifacts, primary, secondary):
    return _oriented(artifacts, pair_hash(primary, secondary), pair_hash(secondary, primary))


def _oriented(artifacts, forward, backward):
    """The alignment served for a pair, its sides the way the pair is being read: stored
    under the pair's hash in whichever order it was run, the later run where both exist."""

    direct = artifacts.get(forward)
    reverse = artifacts.get(backward, {})
    if direct is not None and direct.get("provenance", {}).get("created_at", "") >= reverse.get(
        "provenance", {}
    ).get("created_at", ""):
        return direct
    result = {
        **reverse,
        "groups": [
            {**group, "primary": group["secondary"], "secondary": group["primary"]}
            for group in reverse.get("groups", [])
        ],
    }
    if "primary_spans" in reverse:
        result["primary_spans"] = reverse["secondary_spans"]
        result["secondary_spans"] = reverse["primary_spans"]
    return result
