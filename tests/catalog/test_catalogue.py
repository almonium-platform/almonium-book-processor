"""The public catalogue groups editions by work and orders the groups by urgency."""

from __future__ import annotations

import datetime
import uuid

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from almonium_book_processor.catalog.catalogue import (
    catalogue_groups,
    catalogue_summary,
    display_title,
    import_rows,
    uploaded_label,
    word_count_label,
)
from almonium_book_processor.catalog.models import Edition, PipelineRun, QAWarning, Work

pytestmark = pytest.mark.django_db


@pytest.fixture
def staff(client):
    user = get_user_model().objects.create_user(username="staff", is_staff=True)
    client.force_login(user)
    return user


def _work(slug, title, author, **extra):
    return Work.objects.create(
        slug=slug, title=title, author=author, original_language="en", **extra
    )


def _edition(work, language, status=Edition.Status.PUBLISHED, **extra):
    extra.setdefault("title", work.title)
    extra.setdefault("author", work.author)
    return Edition.objects.create(
        work=work,
        slug=f"{work.slug}-{language}-{extra.get('edition_type', 'original')}",
        language=language,
        status=status,
        **extra,
    )


@pytest.fixture
def frankenstein():
    work = _work("frankenstein", "Frankenstein; or, the Modern Prometheus", "Mary Shelley")
    original = _edition(work, "en", cefr_level="C1", word_count=77706)
    _edition(
        work,
        "fr",
        Edition.Status.REVIEW,
        title="FRANKENSTEIN, OU LE PROMÉTHÉE MODERNE",
        edition_type=Edition.EditionType.HUMAN_TRANSLATION,
        parallel_role=Edition.ParallelRole.STANDALONE,
        word_count=75504,
    )
    _edition(
        work,
        "uk",
        title="Франкенштейн, або Сучасний Прометей",
        source_edition=original,
        edition_type=Edition.EditionType.MACHINE_TRANSLATION,
        parallel_role=Edition.ParallelRole.PARALLEL,
        cefr_level="C1",
        word_count=70000,
    )
    _edition(
        work,
        "en",
        title="Frankenstein; or, the Modern Prometheus",
        source_edition=original,
        edition_type=Edition.EditionType.ADAPTATION,
        parallel_role=Edition.ParallelRole.PARALLEL,
        cefr_level="B2",
        word_count=76295,
    )
    return work


def test_display_title_calms_a_shouting_source_title_and_leaves_the_rest_alone():
    assert display_title("FRANKENSTEIN, OU LE PROMÉTHÉE MODERNE") == (
        "Frankenstein, ou le Prométhée Moderne"
    )
    assert display_title("THE PICTURE OF DORIAN GRAY") == "The Picture of Dorian Gray"
    assert display_title("L'ÉTRANGER") == "L'étranger"
    assert display_title("Bleak House") == "Bleak House"
    assert display_title("") == ""


def test_word_counts_are_spaced_by_thousands():
    assert word_count_label(77706) == "77 706 words"
    assert word_count_label(1) == "1 word"


def test_rows_follow_the_parallel_tree_and_titles_repeat_only_when_they_differ(frankenstein):
    (group,) = catalogue_groups(Work.Visibility.PUBLIC)

    assert group.title == "Frankenstein; or, the Modern Prometheus"
    assert [(row.language, row.role_label) for row in group.rows] == [
        ("EN", "Canonical"),
        ("EN", "Parallel"),
        ("UK", "Parallel"),
        ("FR", "Standalone"),
    ]
    original, adaptation, ukrainian, french = group.rows
    # The original and the adaptation carry the work's title, so the row says
    # only what kind of edition it is.
    assert original.title is None and original.type_label == "Original"
    assert adaptation.title is None and adaptation.type_label == "Level adaptation"
    assert ukrainian.title == "Франкенштейн, або Сучасний Прометей"
    assert french.title == "Frankenstein, ou le Prométhée Moderne"
    # A block-for-block translation reads its source's word count; an
    # adaptation in the same language has its own text to count.
    assert ukrainian.words_label == "from EN"
    assert adaptation.words_label == "76 295 words"
    assert french.words_label == "75 504 words"
    assert group.rollup.label == "1 needs review"
    assert group.rollup.in_flight is False


def test_works_are_ordered_by_urgency_then_surname():
    settled = _work("bleak-house", "Bleak House", "Charles Dickens")
    _edition(settled, "en", Edition.Status.READY)
    later_surname = _work("wuthering-heights", "Wuthering Heights", "Emily Brontë")
    _edition(later_surname, "en", Edition.Status.READY)
    urgent = _work("all-quiet", "All Quiet on the Western Front", "Erich Maria Remarque")
    _edition(urgent, "en", Edition.Status.FAILED)
    busy = _work("dracula", "Dracula", "Bram Stoker")
    _edition(busy, "en", Edition.Status.PROCESSING)

    groups = catalogue_groups(Work.Visibility.PUBLIC)

    assert [group.work.slug for group in groups] == [
        "all-quiet",
        "dracula",
        "wuthering-heights",
        "bleak-house",
    ]
    assert groups[0].rollup.label == "1 failed"
    assert groups[1].rollup.label == "1 processing"
    assert groups[1].rollup.in_flight is True
    assert groups[2].rollup is None
    assert catalogue_summary(groups).label == "4 works · 4 editions · 1 failed · 1 processing"


def test_the_catalogue_page_draws_one_panel_per_work(client, staff, frankenstein):
    QAWarning.objects.create(
        edition=Edition.objects.get(language="fr"),
        code="x",
        severity=QAWarning.Severity.WARNING,
        message="check",
    )
    other = _work("bleak-house", "Bleak House", "Charles Dickens")
    _edition(other, "en", Edition.Status.READY, word_count=353402)

    page = client.get(reverse("catalog:dashboard")).content.decode()

    assert page.count('<article class="work-group">') == 2
    assert page.index("Frankenstein; or, the Modern Prometheus") < page.index("Bleak House")
    assert "2 works · 5 editions · 1 needs review" in page
    assert "Mary Shelley · 4 editions" in page
    assert "Charles Dickens · 1 edition" in page
    assert '<span class="status status-review">1 needs review</span>' in page
    assert 'class="edition-row edition-row-review"' in page
    assert 'edition-warnings edition-warnings-urgent">1 warning<' in page
    assert "Frankenstein, ou le Prométhée Moderne" in page
    assert "FRANKENSTEIN, OU LE" not in page
    assert "from EN" in page
    assert "Canonical original" not in page
    assert page.count('class="role-badge role-badge-parallel">Parallel<') == 2
    assert "Active processing" not in page
    assert "Runs" not in page
    # The button keeps the upload entry point; the navigation no longer repeats it.
    nav, body = page.split("</header>", 1)
    assert "Upload source" not in nav
    assert "Upload source" in body


def test_a_running_stage_replaces_the_status_pill_on_its_row(client, staff):
    work = _work("wuthering-heights", "Wuthering Heights", "Emily Brontë")
    original = _edition(work, "en", Edition.Status.READY, word_count=115517)
    pending = _edition(
        work,
        "uk",
        Edition.Status.PROCESSING,
        title="",
        source_edition=original,
        edition_type=Edition.EditionType.MACHINE_TRANSLATION,
        parallel_role=Edition.ParallelRole.PARALLEL,
    )
    PipelineRun.objects.create(
        edition=pending,
        stage=PipelineRun.Stage.TRANSLATE_METADATA,
        status=PipelineRun.Status.RUNNING,
        progress=14,
        processor_version="test",
        input_hash="x",
        idempotency_key="pending:translate_metadata",
    )

    page = client.get(reverse("catalog:dashboard")).content.decode()

    assert '<span class="rollup-stage">1 processing</span>' in page
    assert '<span class="edition-title-pending">Title pending</span>' in page
    assert "Metadata translation" in page
    assert 'style="width:14%"' in page
    assert "status-processing" not in page
    assert "1 work · 2 editions · 1 processing" in page


def _promote(edition, target, status=PipelineRun.Status.SUCCEEDED, error=""):
    return PipelineRun.objects.create(
        edition=edition,
        stage=PipelineRun.Stage.PROMOTE,
        status=status,
        processor_version="test",
        input_hash="",
        idempotency_key=f"{edition.id}:promote:{target}:{uuid.uuid4().hex}",
        summary={"target": target},
        error=error,
    )


def test_every_approved_row_carries_one_token_per_promotion_target(client, staff, monkeypatch):
    monkeypatch.setenv("ALMONIUM_BOOKS_PROMOTION_TARGETS", "staging=https://staging.example")
    monkeypatch.setenv("ALMONIUM_BOOKS_PROMOTION_TOKEN_STAGING", "secret")
    work = _work("frankenstein", "Frankenstein", "Mary Shelley")
    current = _edition(work, "en", cefr_level="C1")
    _promote(current, "staging")
    behind = _edition(
        work,
        "uk",
        source_edition=current,
        edition_type=Edition.EditionType.MACHINE_TRANSLATION,
        parallel_role=Edition.ParallelRole.PARALLEL,
    )
    _promote(behind, "staging")
    from almonium_book_processor.catalog.models import EditionArtifact

    EditionArtifact.objects.create(
        edition=behind, kind="lexical_profile", input_hash="x", processor_version="v"
    )
    failed = _edition(
        work,
        "fr",
        Edition.Status.READY,
        edition_type=Edition.EditionType.HUMAN_TRANSLATION,
        parallel_role=Edition.ParallelRole.STANDALONE,
    )
    _promote(failed, "staging", PipelineRun.Status.FAILED, error="staging refused the bundle")
    _edition(
        work,
        "de",
        Edition.Status.READY,
        edition_type=Edition.EditionType.HUMAN_TRANSLATION,
        parallel_role=Edition.ParallelRole.STANDALONE,
    )
    _edition(
        work,
        "es",
        Edition.Status.REVIEW,
        edition_type=Edition.EditionType.HUMAN_TRANSLATION,
        parallel_role=Edition.ParallelRole.STANDALONE,
    )

    (group,) = catalogue_groups(Work.Visibility.PUBLIC)
    by_language = {row.language: row for row in group.rows}
    assert [(t.target, t.state) for t in by_language["EN"].promotions] == [("staging", "current")]
    assert [t.state for t in by_language["UK"].promotions] == ["behind"]
    assert [t.state for t in by_language["FR"].promotions] == ["failed"]
    assert [t.state for t in by_language["DE"].promotions] == ["never"]
    assert by_language["ES"].promotions == []
    assert [rollup.label for rollup in group.promotion_rollups] == [
        "1 failed on staging",
        "1 behind on staging",
    ]
    assert (
        catalogue_summary([group]).label
        == "1 work · 5 editions · 1 needs review · 1 failed on staging · 1 behind on staging"
    )

    page = client.get(reverse("catalog:dashboard")).content.decode()
    assert page.count('class="promotion-token promotion-') == 4
    assert '<span class="promotion-dot"></span>staging</span>' in page
    assert '<span class="promotion-dot"></span>staging behind</span>' in page
    assert '<span class="promotion-dot"></span>staging failed</span>' in page
    assert 'title="The last promotion to staging failed: staging refused the bundle' in page
    assert 'title="Never promoted to staging."' in page
    assert f'data-release="{reverse("catalog:edition-detail", args=[failed.id])}#release"' in page
    assert '<span class="status status-failed">1 failed on staging</span>' in page
    assert '<span class="status status-review">1 behind on staging</span>' in page


def test_an_empty_catalogue_still_offers_the_upload(client, staff):
    page = client.get(reverse("catalog:dashboard")).content.decode()
    assert "No public editions yet" in page
    assert "0 works · 0 editions" in page
    assert "Upload source" in page


def _private_work(slug, title, author, label):
    return Work.objects.create(
        slug=slug,
        title=title,
        author=author,
        original_language="en",
        visibility=Work.Visibility.PRIVATE,
        owner_id=uuid.UUID("8c2f0000-0000-4000-8000-00000000" + "91be"),
        owner_label=label,
    )


def test_user_imports_are_a_flat_list_newest_first_with_the_owner(client, staff):
    older = _private_work("monte-cristo", "Le Comte de Monte-Cristo", "Alexandre Dumas", "marc")
    failed = _edition(older, "fr", Edition.Status.FAILED)
    failed.source_file.name = "sources/x/monte-cristo.epub"
    failed.save(update_fields=["source_file"])
    QAWarning.objects.create(edition=failed, code="x", message="broken")
    newer = _private_work("pending-import", "", "", "lena.k")
    pending = _edition(newer, "de", Edition.Status.PROCESSING, title="", author="")
    pending.source_file.name = "sources/y/upload.xml"
    pending.save(update_fields=["source_file"])
    PipelineRun.objects.create(
        edition=pending,
        stage=PipelineRun.Stage.CHAPTER_ANALYSIS,
        status=PipelineRun.Status.RUNNING,
        progress=62,
        processor_version="test",
        input_hash="x",
        idempotency_key="pending:chapter_analysis",
    )
    released = _private_work("all-quiet", "All Quiet on the Western Front", "E. M. Remarque", "")
    _edition(released, "en", Edition.Status.READY)

    rows = import_rows()
    assert [row.language for row in rows] == ["EN", "DE", "FR"]
    assert rows[1].title == "" and rows[1].source_format == "TEI"
    assert rows[1].owner_label == "@lena.k" and rows[1].owner_id_short == "8c2f…91be"
    assert rows[2].source_format == "EPUB" and rows[2].status_label == "Failed"
    assert rows[0].status_label == "Available" and rows[0].owner_label == ""
    assert all(row.uploaded_label.startswith("Today, ") for row in rows)

    page = client.get(reverse("catalog:private-imports")).content.decode()

    assert page.count('class="edition-row') == 3
    assert page.index("All Quiet") < page.index("Title pending") < page.index("Monte-Cristo")
    assert "<small>Author pending · TEI</small>" in page
    assert "<small>Alexandre Dumas · EPUB</small>" in page
    assert 'title="8c2f0000-0000-4000-8000-0000000091be"' in page
    assert ">8c2f…91be<" in page
    assert 'class="edition-row edition-row-failed"' in page
    assert 'edition-warnings edition-warnings-urgent">1 warning<' in page
    assert 'style="width:62%"' in page
    assert "Active processing" not in page
    assert "Runs" not in page and "words" not in page
    assert '<span class="status status-ready">Available</span>' in page


def test_uploaded_label_is_relative_only_for_today():
    now = timezone.now()
    assert uploaded_label(now) == f"Today, {timezone.localtime(now):%H:%M}"
    earlier = datetime.datetime(2026, 9, 13, 21, 28, tzinfo=datetime.UTC)
    assert uploaded_label(earlier) == "Sep 13, 21:28"
