# Factory-generated parallel translations (ai_translation.create_translation_edition)
# did not copy cefr_level/cefr_level_source from their source edition, so translations
# created after their source's difficulty analysis ended up ready with cefr_level=None
# and failed publication. Backfill every such translation from its source; an editor's
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
        ("catalog", "0053_plan_account_session_pause_limit"),
    ]

    operations = [
        migrations.RunPython(follow_source_level, migrations.RunPython.noop),
    ]
