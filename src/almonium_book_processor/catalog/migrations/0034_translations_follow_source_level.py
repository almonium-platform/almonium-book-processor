# A block-for-block machine translation wears its source's level: generation
# copies it and re-analysis of the source propagates it (17e367e). A
# translation generated after its source was analysed but before that rule
# was deployed got neither, so it still reads "Level pending" and cannot be
# published. Label every such translation from its source now; an editor's
# choice on the translation is left alone.

from django.db import migrations
from django.db.models import F


def follow_source_level(apps, schema_editor):
    Edition = apps.get_model("catalog", "Edition")
    translations = (
        Edition.objects.filter(
            parallel_role="parallel",
            edition_type="machine_translation",
            source_edition__cefr_level__isnull=False,
        )
        .exclude(cefr_level_source="editor")
        .exclude(cefr_level=F("source_edition__cefr_level"))
    )
    for translation in translations.select_related("source_edition"):
        source = translation.source_edition
        Edition.objects.filter(id=translation.id).update(
            cefr_level=source.cefr_level, cefr_level_source=source.cefr_level_source
        )


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0033_seed_canonical_groups_after_backfill"),
    ]

    operations = [
        migrations.RunPython(follow_source_level, migrations.RunPython.noop),
    ]
