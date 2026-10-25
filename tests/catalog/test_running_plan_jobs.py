"""plan-service restart asks this command whether a worker is in the middle of a paid call."""

from io import StringIO

import pytest
from django.core.management import call_command

from almonium_book_processor.catalog.models import Edition, PipelineRun, Work
from almonium_book_processor.catalog.production import VERSION

pytestmark = pytest.mark.django_db


def test_a_running_write_is_listed_but_a_production_ticker_is_not():
    work = Work.objects.create(slug="w", title="A book", author="Author")
    edition = Edition.objects.create(work=work, slug="w-en", language="en")
    for version, key in ((VERSION, "production"), ("b2-book-v1", "book")):
        PipelineRun.objects.create(
            edition=edition,
            stage=PipelineRun.Stage.ADAPT,
            processor_version=version,
            input_hash="",
            idempotency_key=key,
            status=PipelineRun.Status.RUNNING,
        )

    out = StringIO()
    call_command("running_plan_jobs", stdout=out)

    lines = out.getvalue().strip().splitlines()
    assert len(lines) == 1 and "b2-book-v1" in lines[0] and "w-en" in lines[0]
