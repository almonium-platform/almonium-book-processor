"""Classify existing editions and seed canonical block groups.

Canonical originals root the parallel tree, so every one of their blocks gets a
stable ``align_group``. A generated parallel edition later copies that value
instead of inferring a correspondence. Imported non-original editions become
standalone: they stay readable on their own and are never block-synchronised
unless an operator explicitly asks for inferred alignment.
"""

from __future__ import annotations

import uuid

from django.db import migrations


def classify_editions(apps, schema_editor):
    Edition = apps.get_model("catalog", "Edition")
    ContentBlock = apps.get_model("catalog", "ContentBlock")

    Edition.objects.filter(edition_type="original").update(parallel_role="canonical")
    Edition.objects.filter(edition_type="machine_translation").update(parallel_role="parallel")
    Edition.objects.exclude(edition_type__in=["original", "machine_translation"]).update(
        parallel_role="standalone"
    )

    canonical_ids = list(
        Edition.objects.filter(parallel_role="canonical").values_list("id", flat=True)
    )
    for edition_id in canonical_ids:
        blocks = list(
            ContentBlock.objects.filter(edition_id=edition_id, align_group__isnull=True).only("id")
        )
        for block in blocks:
            block.align_group = uuid.uuid4()
        ContentBlock.objects.bulk_update(blocks, ["align_group"], batch_size=1000)


def clear_canonical_groups(apps, schema_editor):
    Edition = apps.get_model("catalog", "Edition")
    ContentBlock = apps.get_model("catalog", "ContentBlock")
    canonical_ids = Edition.objects.filter(parallel_role="canonical").values_list("id", flat=True)
    ContentBlock.objects.filter(edition_id__in=list(canonical_ids)).update(align_group=None)


class Migration(migrations.Migration):
    dependencies = [("catalog", "0014_parallel_role_and_align_group_index")]

    operations = [migrations.RunPython(classify_editions, clear_canonical_groups)]
