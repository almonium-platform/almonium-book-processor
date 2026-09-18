# Chapter analysis becomes the authority on an edition's level. The field
# records who last set it so an editor's choice survives re-analysis, and the
# backfill labels every edition that already has a complete current book
# estimate, so nothing waits for the next analysis to lose its "pending".

from django.db import migrations, models
from django.db.models import Q


def label_from_current_analysis(apps, schema_editor):
    Edition = apps.get_model("catalog", "Edition")
    EditionArtifact = apps.get_model("catalog", "EditionArtifact")
    assessments = EditionArtifact.objects.filter(
        kind="difficulty",
        chapter__isnull=True,
        is_current=True,
        processor_version="book-difficulty-v1",
    ).exclude(edition__edition_type="adaptation")
    for artifact in assessments.select_related("edition"):
        level = artifact.payload.get("cefr_estimate")
        if not artifact.payload.get("complete") or level not in (
            "A1",
            "A2",
            "B1",
            "B2",
            "C1",
            "C2",
        ):
            continue
        edition = artifact.edition
        Edition.objects.filter(
            Q(id=edition.id)
            | Q(
                source_edition=edition,
                parallel_role="parallel",
                edition_type="machine_translation",
            )
        ).update(cefr_level=level, cefr_level_source="analysis")


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0031_source_edition_means_generated_from"),
    ]

    operations = [
        migrations.AddField(
            model_name="edition",
            name="cefr_level_source",
            field=models.CharField(
                blank=True,
                choices=[
                    ("analysis", "Chapter analysis"),
                    ("editor", "Editor"),
                    ("target", "Adaptation target"),
                ],
                help_text=(
                    "Who last set the level. Chapter analysis fills it in and keeps it "
                    "current unless an editor chose a level; blank is an unclaimed value, "
                    "such as an upload-time guess, that analysis may replace."
                ),
                max_length=10,
            ),
        ),
        migrations.RunPython(label_from_current_analysis, migrations.RunPython.noop),
    ]
