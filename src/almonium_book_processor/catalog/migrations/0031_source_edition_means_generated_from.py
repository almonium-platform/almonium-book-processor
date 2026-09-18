# A source edition names what an edition was generated from, block for block,
# so only a parallel edition carries one. Imported human translations were
# given one at upload to pick their work and to drive inferred alignment; the
# work link already holds them, and inferred alignment now finds the canonical
# edition itself. Their alignment rows keep their own source reference.

from django.db import migrations, models
import django.db.models.deletion


def detach_imported_editions(apps, schema_editor):
    Edition = apps.get_model("catalog", "Edition")
    Edition.objects.exclude(parallel_role="parallel").filter(
        source_edition__isnull=False
    ).update(source_edition=None)


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0030_work_adaptation_floor"),
    ]

    operations = [
        migrations.AlterField(
            model_name="edition",
            name="source_edition",
            field=models.ForeignKey(
                blank=True,
                help_text=(
                    "The edition this one was generated from, block for block. Set on "
                    "parallel editions only: an independently imported text names its "
                    "work and nothing else, and its correspondence to the canonical text, "
                    "if wanted, is inferred on demand."
                ),
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="derived_editions",
                to="catalog.edition",
            ),
        ),
        migrations.RunPython(detach_imported_editions, migrations.RunPython.noop),
    ]
