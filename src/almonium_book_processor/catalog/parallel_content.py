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
    left = {b.align_group: b for b in primary if b.align_group}
    right = {b.align_group: b for b in secondary if b.align_group}
    if (
        not primary
        or len(left) != len(primary)
        or len(right) != len(secondary)
        or left.keys() != right.keys()
    ):
        return []
    return [(b, right[b.align_group]) for b in primary]


def inherited_payload(edition, other):
    from almonium_book_processor.catalog.offline_sentence_alignment import (
        available_models,
        processor_version,
    )

    pairs = inherited_pairs(edition, other)
    if not pairs:
        return None
    candidates = EditionArtifact.objects.filter(
        edition__in=[edition, other],
        kind=EditionArtifact.Kind.SENTENCE_ALIGNMENT,
        is_current=True,
        processor_version__in=[
            *[processor_version(model) for model in available_models()],
            f"sentence-pair-v2:{settings.OPENAI_TRANSLATION_QUALITY_MODEL}",
        ],
    ).order_by("created_at", "id")
    artifacts = {
        a.input_hash: {
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
        for a in sorted(
            candidates,
            key=lambda a: (
                a.processor_version in [processor_version(model) for model in available_models()]
            ),
        )
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
