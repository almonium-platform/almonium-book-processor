"""Titles and authors are stored the way they are shown: no all-capitals headers.

Sources that shout their title used to be stored verbatim and calmed only by a
template filter, so the edition page's header and its metadata panel disagreed.
Ingestion, the metadata stage and the upload forms now settle the casing once;
this brings the rows already stored in line with what they would store today.
The product API keeps the old values until each environment publishes the
edition again.
"""

from django.db import migrations
from django.utils import timezone

from almonium_book_processor.titles import calm_title


def calm_stored_titles(apps, schema_editor):
    for model_name in ("Work", "Edition"):
        model = apps.get_model("catalog", model_name)
        for row in model.objects.only("title", "author").iterator():
            title, author = calm_title(row.title), calm_title(row.author)
            if (title, author) == (row.title, row.author):
                continue
            model.objects.filter(pk=row.pk).update(
                title=title, author=author, updated_at=timezone.now()
            )


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0034_translations_follow_source_level"),
    ]

    operations = [
        migrations.RunPython(calm_stored_titles, migrations.RunPython.noop),
    ]
