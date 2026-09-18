from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0029_edition_description_and_metadata_translation"),
    ]

    operations = [
        migrations.AddField(
            model_name="work",
            name="adapts_to",
            field=models.CharField(blank=True, editable=False, max_length=2, null=True),
        ),
        migrations.AddField(
            model_name="work",
            name="adaptation_evidence",
            field=models.JSONField(blank=True, default=dict, editable=False),
        ),
    ]
