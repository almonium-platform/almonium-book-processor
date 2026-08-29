import django.db.models.deletion
import uuid
from django.conf import settings
from django.db import migrations, models


def mark_latest_artifacts_current(apps, schema_editor):
    EditionArtifact = apps.get_model("catalog", "EditionArtifact")
    EditionArtifact.objects.update(is_current=False)
    seen = set()
    latest_ids = []
    rows = EditionArtifact.objects.order_by("edition_id", "kind", "-created_at").values_list(
        "id", "edition_id", "kind"
    )
    for artifact_id, edition_id, kind in rows.iterator():
        key = (edition_id, kind)
        if key not in seen:
            seen.add(key)
            latest_ids.append(artifact_id)
    EditionArtifact.objects.filter(id__in=latest_ids).update(is_current=True)


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0012_editionartifact_lexical_stage"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AlterField(
            model_name="pipelinerun",
            name="stage",
            field=models.CharField(
                choices=[
                    ("ingest", "Source ingestion"),
                    ("sentences", "Sentence splitting"),
                    ("align", "Alignment"),
                    ("lexical", "Lexical analysis"),
                    ("source_qa", "Source text QA"),
                    ("translate", "Translation"),
                    ("adapt", "Level adaptation"),
                    ("publish", "Publication"),
                ],
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="editionartifact",
            name="is_current",
            field=models.BooleanField(default=True),
        ),
        migrations.RunPython(mark_latest_artifacts_current, migrations.RunPython.noop),
        migrations.CreateModel(
            name="TextQualityFinding",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("stable_block_id", models.CharField(blank=True, max_length=80)),
                ("input_hash", models.CharField(max_length=64)),
                ("fingerprint", models.CharField(max_length=64)),
                ("code", models.CharField(max_length=100)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("open", "Open"),
                            ("applied", "Correction applied"),
                            ("dismissed", "Dismissed"),
                            ("superseded", "Superseded by a text revision"),
                        ],
                        default="open",
                        max_length=20,
                    ),
                ),
                ("start_offset", models.PositiveIntegerField(blank=True, null=True)),
                ("end_offset", models.PositiveIntegerField(blank=True, null=True)),
                ("original_text", models.TextField(blank=True)),
                ("suggested_text", models.TextField(blank=True)),
                ("confidence", models.FloatField()),
                ("message", models.TextField()),
                ("evidence", models.JSONField(blank=True, default=dict)),
                ("reviewed_at", models.DateTimeField(blank=True, null=True)),
                (
                    "artifact",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="text_quality_findings",
                        to="catalog.editionartifact",
                    ),
                ),
                (
                    "block",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="text_quality_findings",
                        to="catalog.contentblock",
                    ),
                ),
                (
                    "edition",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="text_quality_findings",
                        to="catalog.edition",
                    ),
                ),
                (
                    "pipeline_run",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="text_quality_findings",
                        to="catalog.pipelinerun",
                    ),
                ),
                (
                    "reviewed_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="reviewed_text_quality_findings",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["status", "-confidence", "created_at"],
                "indexes": [
                    models.Index(
                        fields=["edition", "status", "created_at"],
                        name="catalog_text_ed_status_idx",
                    )
                ],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("edition", "input_hash", "fingerprint"),
                        name="catalog_text_finding_input_fingerprint_unique",
                    )
                ],
            },
        ),
    ]
