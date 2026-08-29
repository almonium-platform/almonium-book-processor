import django.db.models.deletion
import uuid
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0011_airun_cached_input_tokens_airun_finished_at_and_more"),
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
                    ("translate", "Translation"),
                    ("adapt", "Level adaptation"),
                    ("publish", "Publication"),
                ],
                max_length=20,
            ),
        ),
        migrations.CreateModel(
            name="EditionArtifact",
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
                (
                    "kind",
                    models.CharField(
                        choices=[
                            ("lexical_profile", "Lexical profile"),
                            ("useful_words", "Useful words"),
                            ("source_qa", "Source text QA"),
                            ("difficulty", "Difficulty assessment"),
                            ("description", "Generated description"),
                            ("chapter_summary", "Chapter summary"),
                            ("quiz", "Quiz"),
                        ],
                        max_length=40,
                    ),
                ),
                ("schema_version", models.PositiveSmallIntegerField(default=1)),
                ("input_hash", models.CharField(max_length=64)),
                ("processor_version", models.CharField(max_length=80)),
                ("payload", models.JSONField(default=dict)),
                (
                    "edition",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="artifacts",
                        to="catalog.edition",
                    ),
                ),
                (
                    "pipeline_run",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="artifacts",
                        to="catalog.pipelinerun",
                    ),
                ),
            ],
            options={
                "ordering": ["-created_at"],
                "indexes": [
                    models.Index(
                        fields=["edition", "kind", "created_at"],
                        name="catalog_art_edition_kind_idx",
                    )
                ],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("edition", "kind", "input_hash", "processor_version"),
                        name="catalog_artifact_edition_kind_input_processor_unique",
                    )
                ],
            },
        ),
    ]
