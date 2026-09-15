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
    from almonium_book_processor.catalog.offline_sentence_alignment import processor_version

    pairs = inherited_pairs(edition, other)
    if not pairs:
        return None
    candidates = EditionArtifact.objects.filter(
        edition__in=[edition, other],
        kind=EditionArtifact.Kind.SENTENCE_ALIGNMENT,
        is_current=True,
        processor_version__in=[
            processor_version(),
            f"sentence-pair-v2:{settings.OPENAI_TRANSLATION_QUALITY_MODEL}",
        ],
    ).order_by("created_at", "id")
    artifacts = {
        a.input_hash: a.payload
        for a in sorted(candidates, key=lambda a: a.processor_version == processor_version())
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
                "primary_sentences": p.sentences,
                "secondary_sentences": s.sentences,
                "revision": pair_hash(p, s),
                "sentence_alignment": sentence_groups(artifacts, p, s),
            }
            for p, s in pairs
        ],
    }


def sentence_groups(artifacts, primary, secondary):
    direct = artifacts.get(pair_hash(primary, secondary))
    if direct is not None:
        return direct.get("groups", [])
    # Inversion is exact; unlike composing through a third edition it makes
    # no new semantic inference and needs no paid call.
    reverse = artifacts.get(pair_hash(secondary, primary), {})
    return [
        {"primary": group["secondary"], "secondary": group["primary"], "certain": group["certain"]}
        for group in reverse.get("groups", [])
    ]
