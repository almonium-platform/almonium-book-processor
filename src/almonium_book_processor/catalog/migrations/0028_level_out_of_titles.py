"""Titles carry no level, and the Ukrainian Frankenstein carries a Ukrainian title.

Editions never get reprocessed, so what an earlier generator wrote into a title
stays until something rewrites it. The generated B2 editions were titled
"<source title> — B2 adaptation"; the level belongs in ``cefr_level`` and shows
as a chip. The machine translation of Frankenstein into Ukrainian was titled in
English on every environment; a reader of the Ukrainian edition should see the
title and author as they are known in Ukrainian, and the product page shows the
original title once beside it. The product API keeps the old values until each
environment publishes the edition again.
"""

import re

from django.db import migrations
from django.utils import timezone

LEVEL_SUFFIX = re.compile(r"\s+—\s+[ABC][12] adaptation$")

UKRAINIAN_FRANKENSTEIN = {
    "slug": "shelley-frankenstein-uk-parallel",
    "title": "Франкенштейн, або Сучасний Прометей",
    "author": "Мері Шеллі",
}


def strip_levels_and_localise(apps, schema_editor):
    Edition = apps.get_model("catalog", "Edition")
    for edition in Edition.objects.filter(title__regex=r" — [ABC][12] adaptation$"):
        edition.title = LEVEL_SUFFIX.sub("", edition.title)
        edition.save(update_fields=["title", "updated_at"])
    Edition.objects.filter(slug=UKRAINIAN_FRANKENSTEIN["slug"], language="uk").update(
        title=UKRAINIAN_FRANKENSTEIN["title"],
        author=UKRAINIAN_FRANKENSTEIN["author"],
        updated_at=timezone.now(),
    )


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0027_drop_promotion_target"),
    ]

    operations = [
        migrations.RunPython(strip_levels_and_localise, migrations.RunPython.noop),
    ]
