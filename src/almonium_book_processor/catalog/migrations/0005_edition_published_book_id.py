from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("catalog", "0004_reviewdecision_and_warning_severity")]

    operations = [
        migrations.AddField(
            model_name="edition",
            name="published_book_id",
            field=models.UUIDField(blank=True, null=True),
        ),
    ]
