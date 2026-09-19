"""The edition page's rail: its next step, its review groups, and the work tree."""

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from almonium_book_processor.catalog.edition_page import next_step, review_groups
from almonium_book_processor.catalog.models import (
    Chapter,
    ContentBlock,
    Edition,
    PipelineRun,
    QAWarning,
    Work,
)
from almonium_book_processor.catalog.review_items import review_items

pytestmark = pytest.mark.django_db


@pytest.fixture
def staff():
    user = get_user_model().objects.create_user("editor", "editor@example.test", "pw")
    user.is_staff = True
    user.save(update_fields=["is_staff"])
    return user


@pytest.fixture
def work():
    return Work.objects.create(
        slug="shelley-frankenstein",
        title="Frankenstein; or, the Modern Prometheus",
        author="Mary Shelley",
        original_language="en",
        publication_year=1818,
    )


@pytest.fixture
def french(work):
    edition = Edition.objects.create(
        work=work,
        slug="shelley-frankenstein-fr",
        title="Frankenstein, ou le Prométhée Moderne",
        author="Mary Shelley",
        language="fr",
        parallel_role="standalone",
        edition_type="human_translation",
        status="review",
        source_sha256="f" * 64,
    )
    for sequence in (3, 27):
        chapter = Chapter.objects.create(edition=edition, sequence=sequence, title=f"Ch {sequence}")
        ContentBlock.objects.create(
            edition=edition,
            chapter=chapter,
            block_id=f"c{sequence}.p2",
            sequence=1,
            text="Texte.",
        )
    return edition


def _low_confidence(edition, block_id, confidence):
    return QAWarning.objects.create(
        edition=edition,
        block=edition.blocks.get(block_id=block_id),
        code="alignment_low_confidence",
        severity=QAWarning.Severity.WARNING,
        message=f"Automatic alignment confidence is {confidence}; review this alignment group.",
    )


def test_review_items_group_by_code_with_the_worst_confidence_first(french):
    _low_confidence(french, "c3.p2", "72.0%")
    _low_confidence(french, "c27.p2", "53.7%")
    QAWarning.objects.create(
        edition=french,
        code="image_without_source",
        severity=QAWarning.Severity.WARNING,
        message="Skipped image without a src attribute",
    )

    groups = review_groups(review_items(french))

    assert [group.code for group in groups] == ["alignment_low_confidence", "image_without_source"]
    alignment, image = groups
    assert alignment.range_label == "2 · 53.7–72.0% · ch. 3–27"
    assert [row.block_label for row in alignment.rows] == ["c27.p2", "c3.p2"]
    assert alignment.rows[0].confidence_class == "confidence-low"
    assert alignment.rows[1].confidence_class == "confidence-mid"
    assert alignment.rows[0].text == "Alignment group needs a look"
    assert alignment.has_confidence and not image.has_confidence
    assert image.range_label == "1"
    assert image.rows[0].text == "Skipped image without a src attribute"
    assert image.rows[0].block_label == ""


def _context(edition, **overrides):
    context = {
        "is_private": False,
        "active_runs": [],
        "actionable_warnings": [],
        "release_rows": [],
        "adaptation_blocker": "",
        "adaptation_target": "",
        "publish_blocked": "",
        "publication_stale": False,
        "projection_state": "",
    }
    context.update(overrides)
    return next_step(edition, context)


def test_the_next_step_follows_the_workflow(french):
    warning = _low_confidence(french, "c3.p2", "50.0%")
    step = _context(french, actionable_warnings=[warning])
    assert step["kind"] == "resolve"
    assert step["text"] == "Resolve the 1 remaining review item, then approve."

    step = _context(french, adaptation_blocker="Chapter 3 is above B2.")
    assert step["kind"] == "gate" and "difficulty gate is not passing" in step["text"]

    step = _context(french, adaptation_target="B2")
    assert step["kind"] == "approve" and "labels it B2" in step["text"]

    french.status = Edition.Status.READY
    step = _context(french, publish_blocked="A CEFR level is required before publication.")
    assert step["kind"] == "publish"
    assert step["blocked"] == step["text"] == "A CEFR level is required before publication."
    assert _context(french).get("blocked") is None

    french.status = Edition.Status.PUBLISHED
    assert _context(french, publication_stale=True)["kind"] == "update"
    rows = [{"target": "staging", "state": "never", "corrections": 0, "artifacts": 0}]
    step = _context(french, release_rows=rows)
    assert step["kind"] == "promote" and step["target"] == "staging"
    rows = [{"target": "staging", "state": "behind", "corrections": 2, "artifacts": 1}]
    assert "2 corrections and 1 new artifact" in _context(french, release_rows=rows)["text"]
    rows = [{"target": "staging", "state": "current", "corrections": 0, "artifacts": 0}]
    assert _context(french, release_rows=rows)["kind"] == "done"

    french.status = Edition.Status.FAILED
    assert _context(french)["kind"] == "retry"

    run = PipelineRun(edition=french, stage=PipelineRun.Stage.ALIGN, progress=40)
    step = _context(french, active_runs=[run])
    assert step["kind"] == "running" and step["text"].startswith("Alignment is running")


def test_a_private_import_is_repaired_and_released_rather_than_approved(french):
    french.work.visibility = Work.Visibility.PRIVATE
    assert _context(french, is_private=True)["kind"] == "repair"
    french.status = Edition.Status.READY
    assert _context(french, is_private=True)["kind"] == "available"


def test_the_page_groups_items_and_resolves_a_whole_group_at_once(client, staff, french):
    for block_id, confidence in (("c3.p2", "72.0%"), ("c27.p2", "53.7%")):
        _low_confidence(french, block_id, confidence)
    client.force_login(staff)

    page = client.get(reverse("catalog:edition-detail", args=[french.id])).content.decode()

    assert "2 open · 1 kind" in page
    assert "<h1>Frankenstein, ou le Prométhée Moderne</h1>" in page
    assert "Mary Shelley · 1818" in page
    assert "Resolve the 2 remaining review items, then approve." in page
    assert 'class="review-row-confidence confidence-low">53.7%' in page
    assert page.index("c27.p2") < page.index("c3.p2")  # lowest confidence first
    assert "Resolve all 2" in page
    assert "Publish after approval" in page  # the Release row, disabled until reviewed
    assert "Content preview" not in page

    response = client.post(
        reverse("catalog:resolve-warnings-by-code", args=[french.id]),
        {"code": "alignment_low_confidence"},
    )

    assert response.status_code == 302
    assert not french.warnings.filter(resolved_at=None).exists()
    assert set(french.warnings.values_list("resolved_by", flat=True)) == {staff.id}
    page = client.get(reverse("catalog:edition-detail", args=[french.id])).content.decode()
    assert "next-step-approve" in page and "Complete review" in page


def test_resolving_one_item_from_the_page_returns_to_the_page(client, staff, french, work):
    Edition.objects.create(
        work=work,
        slug="shelley-frankenstein-en",
        title="Frankenstein",
        author="Mary Shelley",
        language="en",
        parallel_role="canonical",
        status="published",
        source_sha256="e" * 64,
    )
    warning = _low_confidence(french, "c3.p2", "50.0%")
    client.force_login(staff)

    response = client.post(
        reverse("catalog:resolve-warning", args=[french.id, warning.id]), {"return": "edition"}
    )

    assert response["Location"] == reverse("catalog:edition-detail", args=[french.id])
    page = client.get(reverse("catalog:edition-detail", args=[french.id])).content.decode()
    rail = page.split('<div class="rail-tree">')[1].split("</div>")[0]
    assert rail.index("EN") < rail.index("FR")
    assert "This edition" in rail and "Published" in rail
