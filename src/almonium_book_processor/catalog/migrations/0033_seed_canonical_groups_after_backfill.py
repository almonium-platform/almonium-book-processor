# Migration 0015 seeded block groups once, for the canonical originals that
# existed on the day it ran; normalization then kept creating canonical blocks
# without one, so every original ingested since roots nothing and its
# translations inherited NULL. Normalization now mints the groups itself. This
# seeds the originals it missed and carries each group to the parallel blocks
# with the same block id, which the translator echoes, so those pairs become
# readable side by side without a paid re-run.

import uuid

from django.db import migrations


def seed_missing_groups(apps, schema_editor):
    Edition = apps.get_model("catalog", "Edition")
    ContentBlock = apps.get_model("catalog", "ContentBlock")

    ungrouped = Edition.objects.filter(
        parallel_role="canonical", blocks__align_group__isnull=True
    ).distinct()
    for canonical in ungrouped:
        blocks = list(canonical.blocks.filter(align_group__isnull=True).only("id"))
        for block in blocks:
            block.align_group = uuid.uuid4()
        ContentBlock.objects.bulk_update(blocks, ["align_group"], batch_size=1000)

        groups = dict(canonical.blocks.values_list("block_id", "align_group"))
        # Parallels of parallels copied the same NULL; walk the whole subtree.
        sources = [canonical.id]
        while sources:
            parallels = list(
                Edition.objects.filter(source_edition_id__in=sources, parallel_role="parallel")
            )
            for parallel in parallels:
                inherited = list(
                    parallel.blocks.filter(align_group__isnull=True, block_id__in=groups).only(
                        "id", "block_id"
                    )
                )
                for block in inherited:
                    block.align_group = groups[block.block_id]
                ContentBlock.objects.bulk_update(inherited, ["align_group"], batch_size=1000)
            sources = [parallel.id for parallel in parallels]


class Migration(migrations.Migration):
    dependencies = [("catalog", "0032_edition_cefr_level_source")]

    operations = [migrations.RunPython(seed_missing_groups, migrations.RunPython.noop)]
