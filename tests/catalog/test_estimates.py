import uuid
from decimal import Decimal

import pytest

from almonium_book_processor.catalog import estimates
from almonium_book_processor.catalog.chapter_analysis import analysis_spec, snapshot
from almonium_book_processor.catalog.models import (
    AIRun,
    Chapter,
    ContentBlock,
    Edition,
    ModelConfiguration,
    PromptTemplate,
    Work,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def edition():
    work = Work.objects.create(slug="priced-work", title="Priced", author="Writer")
    edition = Edition.objects.create(
        work=work,
        slug="priced-work-en",
        title="Priced",
        author="Writer",
        language="en",
        status=Edition.Status.PUBLISHED,
        source_sha256="b" * 64,
    )
    for sequence in (1, 2):
        chapter = Chapter.objects.create(edition=edition, sequence=sequence, title=str(sequence))
        ContentBlock.objects.create(
            edition=edition,
            chapter=chapter,
            block_id=f"c{sequence}.p1",
            sequence=sequence,
            block_type=ContentBlock.BlockType.PARAGRAPH,
            text="A long sentence about the valley and its river. " * 80,
            align_group=uuid.uuid4(),
        )
    return edition


def test_chapter_analysis_prices_only_windows_not_yet_answered(edition):
    full = estimates.chapter_analysis(edition)
    assert full.usd > 0 and "2 of 2 windows" in full.note
    window = snapshot(edition, analysis_spec("en"))["windows"][0]
    AIRun.objects.create(
        edition=edition,
        input_hash=window["hash"],
        status=AIRun.Status.SUCCEEDED,
        model_configuration=ModelConfiguration.objects.create(
            name="analysis", provider="openai", model="luna", purpose="chapter-analysis"
        ),
        prompt_template=PromptTemplate.objects.create(
            name="analysis", version=1, purpose="chapter-analysis", system_prompt="s"
        ),
    )
    half = estimates.chapter_analysis(edition)
    assert "1 of 2 windows" in half.note
    assert half.usd == pytest.approx(full.usd / 2, rel=Decimal("0.05"))


def test_pilot_follows_the_chapter_and_refuses_what_it_cannot_price(edition):
    first, second = edition.chapters.order_by("sequence")
    prices = estimates.EditionEstimates(edition).pilots["B2"]
    assert set(prices) == {str(first.id), str(second.id)}
    assert prices[str(first.id)].usd > 0
    empty = Chapter.objects.create(edition=edition, sequence=3, title="Blank")
    assert estimates.pilot(empty, "B2").label == "AI"


def test_translation_tiers_and_batch_discount(edition):
    prices = estimates.EditionEstimates(edition).translations
    quality, draft = prices["quality|direct"].usd, prices["draft|direct"].usd
    assert quality == pytest.approx(draft * 10, rel=Decimal("0.01"))
    assert prices["quality|batch"].usd == pytest.approx(quality / 2, rel=Decimal("0.01"))
