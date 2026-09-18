"""Canonical block groups are minted at normalization and repaired where missed."""

from __future__ import annotations

import uuid
from importlib import import_module

import pytest
from django.apps import apps

from almonium_book_processor.catalog.models import Chapter, ContentBlock, Edition, PipelineRun, Work
from almonium_book_processor.catalog.parallel_content import inherited_pairs
from almonium_book_processor.catalog.services import persist_artifact
from almonium_book_processor.models import (
    BlockType,
    BookArtifact,
    EditionMetadata,
    SourceMetadata,
)
from almonium_book_processor.models import (
    ContentBlock as ArtifactBlock,
)

pytestmark = pytest.mark.django_db


def artifact_for(edition, block_ids):
    return BookArtifact(
        processor_version="test",
        edition=EditionMetadata(
            edition_slug=edition.slug,
            work_slug=edition.work.slug,
            title=edition.title,
            author=edition.author,
            language=edition.language,
            source=SourceMetadata(format="tei", path="book.xml", sha256="a" * 64),
        ),
        blocks=[
            ArtifactBlock(
                edition_slug=edition.slug,
                block_id=block_id,
                chapter=1,
                seq=index,
                type=BlockType.PARAGRAPH,
                text=f"Paragraph {block_id}.",
            )
            for index, block_id in enumerate(block_ids, start=1)
        ],
    )


def run_for(edition):
    return PipelineRun.objects.create(
        edition=edition,
        stage=PipelineRun.Stage.INGEST,
        processor_version="test",
        input_hash="a" * 64,
        idempotency_key=f"{edition.slug}-{uuid.uuid4()}",
    )


def original(slug="orig", role="canonical", edition_type="original", **extra):
    work = Work.objects.create(
        slug=f"{slug}-work", title="Book", author="Ada", original_language="en"
    )
    return Edition.objects.create(
        slug=slug,
        work=work,
        title="Book",
        author="Ada",
        language="en",
        edition_type=edition_type,
        parallel_role=role,
        status=Edition.Status.PROCESSING,
        **extra,
    )


def test_normalization_mints_a_group_for_every_canonical_block() -> None:
    edition = original()

    persist_artifact(edition, artifact_for(edition, ["c1.p1", "c1.p2", "c1.p3"]), run_for(edition))

    groups = list(edition.blocks.order_by("sequence").values_list("align_group", flat=True))
    assert all(groups)
    assert len(set(groups)) == 3


def test_renormalizing_a_canonical_keeps_the_groups_its_parallels_inherited() -> None:
    edition = original()
    persist_artifact(edition, artifact_for(edition, ["c1.p1", "c1.p2"]), run_for(edition))
    before = dict(edition.blocks.values_list("block_id", "align_group"))
    translation = Edition.objects.create(
        slug="orig-uk",
        work=edition.work,
        title="Book",
        author="Ada",
        language="uk",
        edition_type="machine_translation",
        source_edition=edition,
        parallel_role="parallel",
        status=Edition.Status.READY,
    )
    chapter = Chapter.objects.create(edition=translation, sequence=1)
    for index, (block_id, group) in enumerate(before.items(), start=1):
        ContentBlock.objects.create(
            edition=translation,
            chapter=chapter,
            block_id=block_id,
            sequence=index,
            block_type="paragraph",
            text=f"Абзац {index}.",
            align_group=group,
        )

    # The source is re-normalized with one extra paragraph at the end.
    persist_artifact(edition, artifact_for(edition, ["c1.p1", "c1.p2", "c1.p3"]), run_for(edition))

    after = dict(edition.blocks.values_list("block_id", "align_group"))
    assert after["c1.p1"] == before["c1.p1"]
    assert after["c1.p2"] == before["c1.p2"]
    assert after["c1.p3"] not in before.values()
    # The existing translation still pairs with the two blocks it translated.
    assert translation.blocks.filter(align_group__in=after.values()).count() == 2


def test_normalization_leaves_a_standalone_edition_ungrouped() -> None:
    edition = original(slug="standalone", role="standalone", edition_type="translation")

    persist_artifact(edition, artifact_for(edition, ["c1.p1"]), run_for(edition))

    assert edition.blocks.get().align_group is None


def test_repair_seeds_a_missed_canonical_and_carries_groups_down_its_subtree() -> None:
    migration = import_module(
        "almonium_book_processor.catalog.migrations.0033_seed_canonical_groups_after_backfill"
    )
    canonical = original()
    persist_artifact(canonical, artifact_for(canonical, ["c1.p1", "c1.p2"]), run_for(canonical))
    # What ingestion did before the fix: canonical blocks with no group at all.
    canonical.blocks.update(align_group=None)
    already_grouped = original(slug="grouped")
    persist_artifact(
        already_grouped, artifact_for(already_grouped, ["c1.p1"]), run_for(already_grouped)
    )
    kept_group = already_grouped.blocks.get().align_group

    def parallel(slug, source, block_ids):
        edition = Edition.objects.create(
            slug=slug,
            work=source.work,
            title="Book",
            author="Ada",
            language="uk",
            edition_type="machine_translation",
            source_edition=source,
            parallel_role="parallel",
            status=Edition.Status.READY,
        )
        chapter = Chapter.objects.create(edition=edition, sequence=1)
        for index, block_id in enumerate(block_ids, start=1):
            ContentBlock.objects.create(
                edition=edition,
                chapter=chapter,
                block_id=block_id,
                sequence=index,
                block_type="paragraph",
                text=f"{slug} {index}",
            )
        return edition

    translation = parallel("orig-uk", canonical, ["c1.p1", "c1.p2"])
    nested = parallel("orig-uk-a2", translation, ["c1.p1", "c1.p2"])
    assert inherited_pairs(canonical, translation) == []

    migration.seed_missing_groups(apps, None)

    groups = dict(canonical.blocks.values_list("block_id", "align_group"))
    assert all(groups.values()) and len(set(groups.values())) == 2
    assert dict(translation.blocks.values_list("block_id", "align_group")) == groups
    assert dict(nested.blocks.values_list("block_id", "align_group")) == groups
    assert len(inherited_pairs(canonical, translation)) == 2
    assert len(inherited_pairs(translation, nested)) == 2
    assert already_grouped.blocks.get().align_group == kept_group
