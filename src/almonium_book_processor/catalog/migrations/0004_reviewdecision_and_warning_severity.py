from __future__ import annotations

import uuid

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def classify_existing_warnings(apps, schema_editor):
    del schema_editor
    Edition = apps.get_model("catalog", "Edition")
    QAWarning = apps.get_model("catalog", "QAWarning")

    QAWarning.objects.filter(code="empty_block_skipped").update(severity="info")
    editions_with_actionable_warnings = QAWarning.objects.exclude(severity="info").values("edition_id")
    Edition.objects.filter(status="review").exclude(
        id__in=editions_with_actionable_warnings
    ).update(status="ready")


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("catalog", "0003_alter_edition_source_file_alter_pipelinerun_stage"),
    ]

    operations = [
        migrations.CreateModel(
            name="ReviewDecision",
            fields=[
                (
                    "id",
                    models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "decision",
                    models.CharField(
                        choices=[("complete", "Review completed")],
                        default="complete",
                        max_length=20,
                    ),
                ),
                ("notes", models.TextField(blank=True)),
                ("source_sha256", models.CharField(blank=True, max_length=64)),
                ("actionable_warning_count", models.PositiveIntegerField(default=0)),
                (
                    "edition",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="review_decisions",
                        to="catalog.edition",
                    ),
                ),
                (
                    "reviewer",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="book_review_decisions",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.RunPython(classify_existing_warnings, migrations.RunPython.noop),
    ]
