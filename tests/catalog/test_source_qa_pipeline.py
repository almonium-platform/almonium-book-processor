from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from almonium_book_processor.catalog.models import (
    Chapter,
    ContentBlock,
    ContentBlockRevision,
    Edition,
    EditionArtifact,
    PipelineRun,
    TextQualityFinding,
    Work,
)
from almonium_book_processor.catalog.tasks import analyze_edition_source_quality
from almonium_book_processor.processing.source_qa import SourceQAFinding

pytestmark = pytest.mark.django_db


def edition_with_split_word() -> tuple[Edition, ContentBlock]:
    work = Work.objects.create(
        slug="source-qa-work",
        title="Source QA Work",
        author="Ada Author",
        original_language="en",
    )
    edition = Edition.objects.create(
        slug="source-qa-work-en",
        work=work,
        title=work.title,
        author=work.author,
        language="en",
        edition_type=Edition.EditionType.ORIGINAL,
        source_sha256="a" * 64,
        status=Edition.Status.READY,
    )
    chapter = Chapter.objects.create(edition=edition, sequence=1)
    block = ContentBlock.objects.create(
        edition=edition,
        chapter=chapter,
        block_id="c1.p1",
        sequence=1,
        block_type=ContentBlock.BlockType.PARAGRAPH,
        text="He walked ab road.",
    )
    return edition, block


def finding_for(block: ContentBlock) -> SourceQAFinding:
    return SourceQAFinding(
        block_id=str(block.id),
        stable_block_id=block.block_id,
        code="probable_split_word",
        start_offset=10,
        end_offset=17,
        original_text="ab road",
        suggested_text="abroad",
        confidence=0.9,
        message="Possible split word.",
        evidence={"zipf_gain": 0.4},
    )


def test_source_qa_task_persists_artifact_and_reviewable_finding(client, monkeypatch) -> None:
    edition, block = edition_with_split_word()
    monkeypatch.setattr(
        "almonium_book_processor.catalog.tasks.importlib.metadata.version",
        lambda package: "test",
    )
    monkeypatch.setattr(
        "almonium_book_processor.catalog.tasks.analyze_source_quality",
        lambda blocks, language: [finding_for(block)],
    )

    analyze_edition_source_quality.run(str(edition.id))
    analyze_edition_source_quality.run(str(edition.id))

    artifact = edition.artifacts.get(kind=EditionArtifact.Kind.SOURCE_QA)
    finding = edition.text_quality_findings.get()
    assert artifact.is_current
    assert artifact.payload["finding_count"] == 1
    assert finding.status == TextQualityFinding.Status.OPEN
    assert finding.block == block
    assert edition.pipeline_runs.get(stage=PipelineRun.Stage.SOURCE_QA).status == "succeeded"

    user = get_user_model().objects.create_superuser(
        username="qa-page-editor",
        email="qa-page@example.test",
        password="password",
    )
    client.force_login(user)
    response = client.get(reverse("catalog:edition-detail", args=[edition.id]))
    content = response.content.decode()
    assert response.status_code == 200
    assert "Run lexical analysis" in content
    assert "Scan source text" in content
    assert "Possible split word." in content
    assert ">abroad</textarea>" in content


def test_existing_edition_can_queue_lexical_and_source_qa_from_page(client, monkeypatch) -> None:
    edition, _ = edition_with_split_word()
    user = get_user_model().objects.create_superuser(
        username="qa-queue-editor",
        email="qa-queue@example.test",
        password="password",
    )
    client.force_login(user)
    queued = []
    monkeypatch.setattr(
        "almonium_book_processor.catalog.tasks.analyze_edition_lexicon.delay",
        lambda edition_id: queued.append(("lexical", edition_id)),
    )
    monkeypatch.setattr(
        "almonium_book_processor.catalog.tasks.analyze_edition_source_quality.delay",
        lambda edition_id: queued.append(("source_qa", edition_id)),
    )

    lexical_response = client.post(reverse("catalog:queue-lexical-analysis", args=[edition.id]))
    qa_response = client.post(reverse("catalog:queue-source-quality-scan", args=[edition.id]))

    assert lexical_response.status_code == 302
    assert qa_response.status_code == 302
    assert queued == [("lexical", str(edition.id)), ("source_qa", str(edition.id))]


def test_staff_can_edit_and_apply_source_finding_with_audit(
    client, monkeypatch, django_capture_on_commit_callbacks
) -> None:
    edition, block = edition_with_split_word()
    artifact = EditionArtifact.objects.create(
        edition=edition,
        kind=EditionArtifact.Kind.SOURCE_QA,
        input_hash="b" * 64,
        processor_version="source-qa-v1",
        payload={"finding_count": 1},
    )
    lexical = EditionArtifact.objects.create(
        edition=edition,
        kind=EditionArtifact.Kind.LEXICAL_PROFILE,
        input_hash="b" * 64,
        processor_version="lexical-v1",
        payload={},
    )
    finding = TextQualityFinding.objects.create(
        edition=edition,
        artifact=artifact,
        block=block,
        stable_block_id=block.block_id,
        input_hash=artifact.input_hash,
        fingerprint="c" * 64,
        code="probable_split_word",
        start_offset=10,
        end_offset=17,
        original_text="ab road",
        suggested_text="abroad",
        confidence=0.9,
        message="Possible split word.",
    )
    user = get_user_model().objects.create_superuser(
        username="qa-apply-editor",
        email="qa-apply@example.test",
        password="password",
    )
    client.force_login(user)
    queued = []
    monkeypatch.setattr(
        "almonium_book_processor.catalog.tasks.refresh_edition_after_revision.delay",
        queued.append,
    )

    with django_capture_on_commit_callbacks(execute=True):
        response = client.post(
            reverse("catalog:apply-source-quality-finding", args=[edition.id, finding.id]),
            {"replacement": "abroad", "notes": "Confirmed against another edition."},
        )

    assert response.status_code == 302
    block.refresh_from_db()
    finding.refresh_from_db()
    artifact.refresh_from_db()
    lexical.refresh_from_db()
    revision = ContentBlockRevision.objects.get(edition=edition)
    assert block.text == "He walked abroad."
    assert finding.status == TextQualityFinding.Status.APPLIED
    assert revision.previous_text == "He walked ab road."
    assert revision.notes == "Confirmed against another edition."
    assert not artifact.is_current
    assert not lexical.is_current
    assert queued == [str(edition.id)]


def test_staff_can_dismiss_source_finding(client) -> None:
    edition, block = edition_with_split_word()
    finding = TextQualityFinding.objects.create(
        edition=edition,
        block=block,
        stable_block_id=block.block_id,
        input_hash="b" * 64,
        fingerprint="d" * 64,
        code="probable_split_word",
        start_offset=10,
        end_offset=17,
        original_text="ab road",
        suggested_text="abroad",
        confidence=0.9,
        message="Possible split word.",
    )
    user = get_user_model().objects.create_superuser(
        username="qa-dismiss-editor",
        email="qa-dismiss@example.test",
        password="password",
    )
    client.force_login(user)

    response = client.post(
        reverse("catalog:dismiss-source-quality-finding", args=[edition.id, finding.id])
    )

    finding.refresh_from_db()
    assert response.status_code == 302
    assert finding.status == TextQualityFinding.Status.DISMISSED
    assert finding.reviewed_by == user
