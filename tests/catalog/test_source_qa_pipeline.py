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
from almonium_book_processor.catalog.tasks import (
    align_edition_to_source,
    analyze_edition_source_quality,
    refresh_edition_after_revision,
)
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


def test_staff_can_bulk_approve_high_confidence_detached_initials(
    client, monkeypatch, django_capture_on_commit_callbacks
) -> None:
    edition, first_block = edition_with_split_word()
    first_block.text = "T he answer was clear."
    first_block.save(update_fields=["text", "updated_at"])
    chapter = first_block.chapter
    second_block = ContentBlock.objects.create(
        edition=edition,
        chapter=chapter,
        block_id="c1.p2",
        sequence=2,
        block_type=ContentBlock.BlockType.PARAGRAPH,
        text="\u201cA lice replied.",
    )
    third_block = ContentBlock.objects.create(
        edition=edition,
        chapter=chapter,
        block_id="c1.p3",
        sequence=3,
        block_type=ContentBlock.BlockType.PARAGRAPH,
        text="He walked ab road.",
    )
    artifact = EditionArtifact.objects.create(
        edition=edition,
        kind=EditionArtifact.Kind.SOURCE_QA,
        input_hash="e" * 64,
        processor_version="source-qa-v2",
        payload={"finding_count": 3},
    )
    detached_findings = [
        TextQualityFinding.objects.create(
            edition=edition,
            artifact=artifact,
            block=block,
            stable_block_id=block.block_id,
            input_hash=artifact.input_hash,
            fingerprint=character * 64,
            code="detached_initial",
            start_offset=start,
            end_offset=end,
            original_text=original,
            suggested_text=replacement,
            confidence=confidence,
            message="Possible detached drop cap.",
        )
        for block, character, start, end, original, replacement, confidence in (
            (first_block, "f", 0, 4, "T he", "The", 0.98),
            (second_block, "a", 1, 7, "A lice", "Alice", 0.95),
        )
    ]
    unrelated_finding = TextQualityFinding.objects.create(
        edition=edition,
        artifact=artifact,
        block=third_block,
        stable_block_id=third_block.block_id,
        input_hash=artifact.input_hash,
        fingerprint="9" * 64,
        code="probable_split_word",
        start_offset=10,
        end_offset=17,
        original_text="ab road",
        suggested_text="abroad",
        confidence=0.8,
        message="Possible split word.",
    )
    user = get_user_model().objects.create_superuser(
        username="qa-bulk-editor",
        email="qa-bulk@example.test",
        password="password",
    )
    client.force_login(user)
    queued = []
    monkeypatch.setattr(
        "almonium_book_processor.catalog.tasks.refresh_edition_after_revision.delay",
        queued.append,
    )

    page = client.get(reverse("catalog:edition-detail", args=[edition.id]))
    assert "Approve all high-confidence drop caps" in page.content.decode()

    with django_capture_on_commit_callbacks(execute=True):
        response = client.post(reverse("catalog:approve-detached-initials", args=[edition.id]))

    assert response.status_code == 302
    first_block.refresh_from_db()
    second_block.refresh_from_db()
    artifact.refresh_from_db()
    unrelated_finding.refresh_from_db()
    assert first_block.text == "The answer was clear."
    assert second_block.text == "\u201cAlice replied."
    assert set(
        TextQualityFinding.objects.filter(
            id__in=[finding.id for finding in detached_findings]
        ).values_list("status", flat=True)
    ) == {TextQualityFinding.Status.APPLIED}
    assert unrelated_finding.status == TextQualityFinding.Status.OPEN
    assert ContentBlockRevision.objects.filter(edition=edition).count() == 2
    assert not artifact.is_current
    assert queued == [str(edition.id)]

    refreshing_page = client.get(reverse("catalog:edition-detail", args=[edition.id]))
    content = refreshing_page.content.decode()
    assert "Source-text QA" in content
    assert "derived QA data is refreshing" in content
    assert "Possible split word." in content


def test_revision_refresh_realigns_edited_targets_and_source_derivatives(monkeypatch) -> None:
    source, _ = edition_with_split_word()
    target = Edition.objects.create(
        slug="source-qa-work-fr",
        work=source.work,
        source_edition=source,
        title="Source QA Work FR",
        author=source.author,
        language="fr",
        edition_type=Edition.EditionType.HUMAN_TRANSLATION,
        source_sha256="7" * 64,
    )
    monkeypatch.setattr(
        "almonium_book_processor.catalog.tasks.split_edition_sentences.run", lambda edition_id: None
    )
    monkeypatch.setattr(
        "almonium_book_processor.catalog.tasks.analyze_edition_lexicon.run", lambda edition_id: None
    )
    monkeypatch.setattr(
        "almonium_book_processor.catalog.tasks.analyze_edition_source_quality.run",
        lambda edition_id: None,
    )
    aligned = []
    monkeypatch.setattr(
        "almonium_book_processor.catalog.tasks.align_edition_to_source.run", aligned.append
    )

    refresh_edition_after_revision.run(str(source.id))
    refresh_edition_after_revision.run(str(target.id))

    assert aligned == [str(target.id), str(target.id)]


def test_alignment_is_versioned_by_normalized_content(monkeypatch) -> None:
    source, source_block = edition_with_split_word()
    target = Edition.objects.create(
        slug="source-qa-alignment-fr",
        work=source.work,
        source_edition=source,
        title="Source QA Alignment FR",
        author=source.author,
        language="fr",
        edition_type=Edition.EditionType.HUMAN_TRANSLATION,
        source_sha256="8" * 64,
    )
    target_chapter = Chapter.objects.create(edition=target, sequence=1)
    ContentBlock.objects.create(
        edition=target,
        chapter=target_chapter,
        block_id="c1.p1",
        sequence=1,
        block_type=ContentBlock.BlockType.PARAGRAPH,
        text="Il marcha au loin.",
    )
    monkeypatch.setattr(
        "almonium_book_processor.catalog.tasks.embed_texts",
        lambda texts: [[1.0, 0.0] for _ in texts],
    )

    align_edition_to_source.run(str(target.id))
    source_block.text = "He walked abroad."
    source_block.save(update_fields=["text", "updated_at"])
    align_edition_to_source.run(str(target.id))

    alignment_runs = target.pipeline_runs.filter(stage=PipelineRun.Stage.ALIGN)
    assert alignment_runs.count() == 2
    assert len(set(alignment_runs.values_list("input_hash", flat=True))) == 2


def test_staff_can_queue_alignment_rebuild_from_edition_page(client, monkeypatch) -> None:
    source, _ = edition_with_split_word()
    target = Edition.objects.create(
        slug="source-qa-manual-alignment-fr",
        work=source.work,
        source_edition=source,
        title="Source QA Manual Alignment FR",
        author=source.author,
        language="fr",
        edition_type=Edition.EditionType.HUMAN_TRANSLATION,
        source_sha256="6" * 64,
    )
    user = get_user_model().objects.create_superuser(
        username="alignment-queue-editor",
        email="alignment-queue@example.test",
        password="password",
    )
    client.force_login(user)
    queued = []
    monkeypatch.setattr(
        "almonium_book_processor.catalog.tasks.align_edition_to_source.delay",
        queued.append,
    )

    page = client.get(reverse("catalog:edition-detail", args=[target.id]))
    response = client.post(reverse("catalog:queue-source-alignment", args=[target.id]))

    assert "Build inferred alignment" in page.content.decode()
    assert response.status_code == 302
    assert queued == [str(target.id)]
