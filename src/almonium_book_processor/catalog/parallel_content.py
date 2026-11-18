"""Presentation-free inherited correspondence for generated edition families."""

import hashlib
import json

from django.conf import settings

from almonium_book_processor.catalog.models import EditionArtifact


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


def inherited_pairs(edition, other):
    if (
        edition.id == other.id
        or edition.work_id != other.work_id
        or not edition.supports_parallel_reading
        or not other.supports_parallel_reading
        or canonical_root(edition) != canonical_root(other)
    ):
        return []
    primary = list(
        edition.blocks.select_related("chapter", "edition").order_by(
            "chapter__sequence", "sequence"
        )
    )
    secondary = list(
        other.blocks.select_related("chapter", "edition").order_by("chapter__sequence", "sequence")
    )
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


def inherited_payload(edition, other):
    from almonium_book_processor.catalog.offline_sentence_alignment import (
        available_models,
        processor_version,
    )

    pairs = inherited_pairs(edition, other)
    if not pairs:
        return None
    from django.db.models import Q

    from almonium_book_processor.catalog import sentence_adjudication

    offline = [processor_version(model) for model in available_models()]
    candidates = list(
        EditionArtifact.objects.filter(
            Q(
                processor_version__in=[
                    *offline,
                    f"sentence-pair-v2:{settings.OPENAI_TRANSLATION_QUALITY_MODEL}",
                ]
            )
            | Q(processor_version__startswith=f"{sentence_adjudication.VERSION}:"),
            edition__in=[edition, other],
            kind=EditionArtifact.Kind.SENTENCE_ALIGNMENT,
            is_current=True,
        ).order_by("created_at", "id")
    )

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
                "primary_sentences": aligned_data(artifacts, p, s).get(
                    "primary_spans", p.sentences
                ),
                "secondary_sentences": aligned_data(artifacts, p, s).get(
                    "secondary_spans", s.sentences
                ),
                "alignment_provenance": aligned_data(artifacts, p, s).get("provenance"),
                "revision": pair_hash(p, s),
                "sentence_alignment": sentence_groups(artifacts, p, s),
            }
            for p, s in pairs
        ],
    }


def aligned_data(artifacts, primary, secondary):
    direct = artifacts.get(pair_hash(primary, secondary))
    reverse = artifacts.get(pair_hash(secondary, primary), {})
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


def sentence_groups(artifacts, primary, secondary):
    return aligned_data(artifacts, primary, secondary).get("groups", [])
