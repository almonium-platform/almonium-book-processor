from __future__ import annotations

import json
import uuid
from io import BytesIO

import pytest
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from ebooklib import epub
from rest_framework.test import APIClient

from almonium_book_processor.catalog.admin import EditionAdminForm, WorkAdminForm
from almonium_book_processor.catalog.forms import EditionUploadForm
from almonium_book_processor.catalog.models import (
    AlignmentGroupReview,
    BlockAlignment,
    Chapter,
    ContentBlock,
    ContentBlockRevision,
    Edition,
    PipelineRun,
    QAWarning,
    ReviewDecision,
    Work,
)
from almonium_book_processor.catalog.services import import_legacy_artifact, persist_artifact
from almonium_book_processor.catalog.tasks import (
    align_edition_to_source,
    process_book_pipeline,
    process_normalized_edition,
    process_source_edition,
    publish_edition,
    split_edition_sentences,
)
from almonium_book_processor.models import (
    BlockType,
    BookArtifact,
    EditionMetadata,
    IngestionWarning,
    SourceMetadata,
)
from almonium_book_processor.models import (
    ContentBlock as ArtifactBlock,
)

pytestmark = pytest.mark.django_db


def epub_bytes(tmp_path) -> bytes:
    path = tmp_path / "upload.epub"
    book = epub.EpubBook()
    book.set_identifier("upload-test")
    book.set_title("Upload Test")
    book.set_language("de")
    book.add_author("Ada Author")
    chapter = epub.EpubHtml(title="One", file_name="one.xhtml", lang="de")
    chapter.content = "<h2>Eins</h2><p>Der erste Abschnitt.</p>"
    book.add_item(chapter)
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    book.spine = ["nav", chapter]
    epub.write_epub(path, book)
    return path.read_bytes()


def test_upload_form_collects_reader_metadata(tmp_path) -> None:
    form = EditionUploadForm(
        data={
            "work_slug": "upload-test",
            "work_title": "Upload Test",
            "author": "Ada Author",
            "original_language": "de",
            "publication_year": 1912,
            "cover_url": "https://example.test/public-domain-cover.jpg",
            "edition_slug": "upload-test-de-orig",
            "edition_title": "Upload Test",
            "language": "de",
            "edition_type": Edition.EditionType.ORIGINAL,
            "cefr_level": Edition.CEFRLevel.B2,
        },
        files={"source_file": SimpleUploadedFile("upload.epub", epub_bytes(tmp_path))},
    )

    assert form.is_valid(), form.errors
    assert form.cleaned_data["publication_year"] == 1912
    assert form.cleaned_data["cefr_level"] == Edition.CEFRLevel.B2


def test_upload_form_rejects_unknown_language_code(tmp_path) -> None:
    form = EditionUploadForm(
        data={
            "work_slug": "upload-test",
            "work_title": "Upload Test",
            "author": "Ada Author",
            "original_language": "zz",
            "publication_year": 1912,
            "edition_slug": "upload-test-en-orig",
            "edition_title": "Upload Test",
            "language": "en",
            "edition_type": Edition.EditionType.ORIGINAL,
            "cefr_level": Edition.CEFRLevel.B2,
        },
        files={"source_file": SimpleUploadedFile("upload.epub", epub_bytes(tmp_path))},
    )

    assert not form.is_valid()
    assert "original_language" in form.errors


def test_language_inputs_are_explicit_select_controls() -> None:
    assert EditionUploadForm.base_fields["language"].widget.__class__.__name__ == "Select"
    assert EditionAdminForm.base_fields["language"].widget.__class__.__name__ == "Select"
    assert WorkAdminForm.base_fields["original_language"].widget.__class__.__name__ == "Select"


def test_upload_form_shows_practical_examples() -> None:
    assert (
        EditionUploadForm.base_fields["work_slug"].widget.attrs["placeholder"]
        == "pride-and-prejudice"
    )
    assert (
        EditionUploadForm.base_fields["edition_slug"].widget.attrs["placeholder"]
        == "pride-and-prejudice-en-original"
    )
    assert "underlying literary work" in EditionUploadForm.base_fields["work_title"].help_text
    assert (
        "specific uploaded text/version" in EditionUploadForm.base_fields["edition_title"].help_text
    )


def test_derived_upload_requires_source_lineage(tmp_path) -> None:
    form = EditionUploadForm(
        data={
            "work_slug": "upload-test",
            "work_title": "Upload Test",
            "author": "Ada Author",
            "original_language": "de",
            "publication_year": 1912,
            "edition_slug": "upload-test-en-human",
            "edition_title": "Upload Test",
            "language": "en",
            "edition_type": Edition.EditionType.HUMAN_TRANSLATION,
            "cefr_level": Edition.CEFRLevel.B2,
        },
        files={"source_file": SimpleUploadedFile("upload.epub", epub_bytes(tmp_path))},
    )

    assert not form.is_valid()
    assert "source_edition" in form.errors


def test_derived_upload_accepts_source_from_the_same_work(tmp_path) -> None:
    work = Work.objects.create(
        slug="upload-test",
        title="Upload Test",
        author="Ada Author",
        original_language="de",
    )
    source = Edition.objects.create(
        slug="upload-test-de-original",
        work=work,
        title="Upload Test",
        author="Ada Author",
        language="de",
    )
    form = EditionUploadForm(
        data={
            "work_slug": work.slug,
            "work_title": work.title,
            "author": work.author,
            "original_language": "de",
            "publication_year": 1912,
            "edition_slug": "upload-test-en-human",
            "edition_title": "Upload Test",
            "language": "en",
            "edition_type": Edition.EditionType.HUMAN_TRANSLATION,
            "source_edition": str(source.id),
            "cefr_level": Edition.CEFRLevel.B2,
        },
        files={"source_file": SimpleUploadedFile("upload.epub", epub_bytes(tmp_path))},
    )

    assert form.is_valid(), form.errors
    assert form.cleaned_data["source_edition"] == source


def test_source_upload_queues_the_complete_pipeline(
    tmp_path, monkeypatch, django_capture_on_commit_callbacks
) -> None:
    queued: list[str] = []
    monkeypatch.setattr(
        "almonium_book_processor.catalog.tasks.process_book_pipeline.delay",
        lambda edition_id: queued.append(edition_id),
    )
    form = EditionUploadForm(
        data={
            "work_slug": "queued-upload",
            "work_title": "Queued Upload",
            "author": "Ada Author",
            "original_language": "de",
            "publication_year": 1912,
            "edition_slug": "queued-upload-de-original",
            "edition_title": "Queued Upload",
            "language": "de",
            "edition_type": Edition.EditionType.ORIGINAL,
            "cefr_level": Edition.CEFRLevel.B2,
        },
        files={"source_file": SimpleUploadedFile("upload.epub", epub_bytes(tmp_path))},
    )

    assert form.is_valid(), form.errors
    with django_capture_on_commit_callbacks(execute=True):
        edition = form.save()

    assert queued == [str(edition.id)]


def test_complete_pipeline_runs_ingestion_before_local_nlp(monkeypatch) -> None:
    stages: list[tuple[str, str]] = []
    monkeypatch.setattr(
        "almonium_book_processor.catalog.tasks.process_source_edition.run",
        lambda edition_id: stages.append(("ingest", edition_id)),
    )
    monkeypatch.setattr(
        "almonium_book_processor.catalog.tasks.process_normalized_edition.run",
        lambda edition_id: stages.append(("nlp", edition_id)),
    )

    process_book_pipeline.run("edition-id")

    assert stages == [("ingest", "edition-id"), ("nlp", "edition-id")]


def test_internal_private_import_is_owner_scoped(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("ALMONIUM_BOOKS_PUBLISHER_TOKEN", "test-shared-secret")
    owner_id = uuid.uuid4()
    client = APIClient()
    response = client.post(
        "/api/v1/internal/imports/",
        {
            "import_id": str(uuid.uuid4()),
            "owner_id": str(owner_id),
            "owner_label": "private-reader",
            "title": "Private Test",
            "author": "Ada Author",
            "description": "Only this reader can access it.",
            "language": "de",
            "publication_year": 1912,
            "source_file": SimpleUploadedFile("private.epub", epub_bytes(tmp_path)),
        },
        format="multipart",
        HTTP_X_ALMONIUM_BOOKS_TOKEN="test-shared-secret",
    )

    assert response.status_code == 202
    edition = Edition.objects.select_related("work").get(id=response.data["id"])
    assert edition.work.visibility == Work.Visibility.PRIVATE
    assert edition.work.owner_id == owner_id
    assert edition.work.owner_label == "private-reader"
    assert edition.work.description == "Only this reader can access it."

    hidden = client.get(
        f"/api/v1/internal/imports/{edition.id}/",
        {"owner_id": str(uuid.uuid4())},
        HTTP_X_ALMONIUM_BOOKS_TOKEN="test-shared-secret",
    )
    assert hidden.status_code == 404


def test_epub_task_persists_normalized_content(tmp_path, settings) -> None:
    settings.MEDIA_ROOT = tmp_path / "media"
    work = Work.objects.create(
        slug="upload-test",
        title="Upload Test",
        author="Ada Author",
        original_language="de",
    )
    edition = Edition.objects.create(
        slug="upload-test-de-orig",
        work=work,
        title="Upload Test",
        author="Ada Author",
        language="de",
        source_file=SimpleUploadedFile("upload.epub", epub_bytes(tmp_path)),
        status=Edition.Status.QUEUED,
    )

    process_source_edition.run(str(edition.id))

    edition.refresh_from_db()
    assert edition.status == Edition.Status.READY
    assert edition.source_sha256
    assert edition.chapters.count() == 1
    assert list(edition.blocks.values_list("text", flat=True)) == ["Eins", "Der erste Abschnitt."]
    assert edition.pipeline_runs.get().status == PipelineRun.Status.SUCCEEDED


def test_tei_task_persists_normalized_content(tmp_path, settings) -> None:
    settings.MEDIA_ROOT = tmp_path / "media"
    work = Work.objects.create(
        slug="tei-upload-test",
        title="TEI Upload Test",
        author="Ada Author",
        original_language="en",
    )
    source = b"""<TEI xmlns="http://www.tei-c.org/ns/1.0" xml:lang="en">
      <teiHeader><fileDesc><titleStmt><title>TEI Upload Test</title><author>Ada Author</author>
      </titleStmt><publicationStmt><p/></publicationStmt><sourceDesc><p/></sourceDesc></fileDesc>
      </teiHeader><text><body><div type="chapter"><head>One</head><p>First paragraph.</p>
      </div></body></text></TEI>"""
    edition = Edition.objects.create(
        slug="tei-upload-test-en-orig",
        work=work,
        title="TEI Upload Test",
        author="Ada Author",
        language="en",
        source_file=SimpleUploadedFile("upload.xml", source),
        status=Edition.Status.QUEUED,
    )

    process_source_edition.run(str(edition.id))

    edition.refresh_from_db()
    assert edition.status == Edition.Status.READY
    assert list(edition.blocks.values_list("text", flat=True)) == ["One", "First paragraph."]
    assert edition.pipeline_runs.get().summary["source_format"] == "tei"


def test_informational_import_notice_does_not_require_review() -> None:
    work = Work.objects.create(
        slug="notice-work",
        title="Notice Work",
        author="Ada Author",
        original_language="en",
    )
    edition = Edition.objects.create(
        slug="notice-work-en-orig",
        work=work,
        title="Notice Work",
        author="Ada Author",
        language="en",
        status=Edition.Status.PROCESSING,
    )
    run = PipelineRun.objects.create(
        edition=edition,
        stage=PipelineRun.Stage.INGEST,
        processor_version="test",
        input_hash="a" * 64,
        idempotency_key="notice-work",
    )
    artifact = BookArtifact(
        processor_version="test",
        edition=EditionMetadata(
            edition_slug=edition.slug,
            work_slug=work.slug,
            title=edition.title,
            author=edition.author,
            language="en",
            source=SourceMetadata(format="tei", path="notice.xml", sha256="a" * 64),
        ),
        blocks=[
            ArtifactBlock(
                edition_slug=edition.slug,
                block_id="c1.p1",
                chapter=1,
                seq=1,
                type=BlockType.PARAGRAPH,
                text="Kept text.",
            )
        ],
        warnings=[
            IngestionWarning(
                code="empty_block_skipped",
                message="Skipped empty paragraph element",
            )
        ],
    )

    persist_artifact(edition, artifact, run)

    edition.refresh_from_db()
    warning = edition.warnings.get()
    assert edition.status == Edition.Status.READY
    assert warning.severity == QAWarning.Severity.INFO


def test_staff_can_complete_review_from_the_edition_page(client) -> None:
    staff = get_user_model().objects.create_user(username="reviewer", password="safe-test-password")
    staff.is_staff = True
    staff.save(update_fields=["is_staff"])
    work = Work.objects.create(
        slug="review-work",
        title="Review Work",
        author="Ada Author",
        original_language="en",
    )
    edition = Edition.objects.create(
        slug="review-work-en-orig",
        work=work,
        title="Review Work",
        author="Ada Author",
        language="en",
        source_sha256="b" * 64,
        status=Edition.Status.REVIEW,
    )
    QAWarning.objects.create(
        edition=edition,
        code="image_without_source",
        severity=QAWarning.Severity.WARNING,
        message="Skipped image without a src attribute",
    )
    client.force_login(staff)

    page = client.get(reverse("catalog:edition-detail", args=[edition.id]))
    assert page.status_code == 200
    assert "Resolve the 1 remaining review item" in page.content.decode()
    blocked_response = client.post(
        reverse("catalog:complete-edition-review", args=[edition.id]),
        {"notes": "The missing image is decorative."},
    )
    edition.refresh_from_db()
    assert blocked_response.status_code == 302
    assert edition.status == Edition.Status.REVIEW

    client.post(reverse("catalog:resolve-warning", args=[edition.id, edition.warnings.get().id]))
    response = client.post(
        reverse("catalog:complete-edition-review", args=[edition.id]),
        {"notes": "The missing image is decorative."},
    )

    assert response.status_code == 302
    edition.refresh_from_db()
    decision = ReviewDecision.objects.get(edition=edition)
    assert edition.status == Edition.Status.READY
    assert decision.reviewer == staff
    assert decision.source_sha256 == "b" * 64
    assert decision.actionable_warning_count == 1
    assert decision.notes == "The missing image is decorative."


def alignment_review_records() -> tuple:
    work = Work.objects.create(
        slug="alignment-review-work",
        title="Alignment Review Work",
        author="Ada Author",
        original_language="en",
    )
    source = Edition.objects.create(
        slug="alignment-review-work-en",
        work=work,
        title="Alignment Review Work",
        author="Ada Author",
        language="en",
        source_sha256="1" * 64,
        status=Edition.Status.READY,
    )
    target = Edition.objects.create(
        slug="alignment-review-work-fr",
        work=work,
        source_edition=source,
        title="Œuvre à réviser",
        author="Ada Author",
        language="fr",
        edition_type=Edition.EditionType.HUMAN_TRANSLATION,
        source_sha256="2" * 64,
        status=Edition.Status.REVIEW,
    )
    source_chapter = Chapter.objects.create(edition=source, sequence=1, title="One")
    target_chapter = Chapter.objects.create(edition=target, sequence=1, title="Un")
    source_blocks = [
        ContentBlock.objects.create(
            edition=source,
            chapter=source_chapter,
            block_id=f"c1.p{sequence}",
            sequence=sequence,
            block_type=ContentBlock.BlockType.PARAGRAPH,
            text=text,
        )
        for sequence, text in enumerate(("First source.", "Second source."), start=1)
    ]
    target_blocks = [
        ContentBlock.objects.create(
            edition=target,
            chapter=target_chapter,
            block_id=f"c1.p{sequence}",
            sequence=sequence,
            block_type=ContentBlock.BlockType.PARAGRAPH,
            text=text,
            sentences=[{"id": f"c1.p{sequence}.s1", "start": 0, "end": len(text)}],
        )
        for sequence, text in enumerate(("Première cible.", "Deuxième cible."), start=1)
    ]
    group_id = uuid.uuid4()
    BlockAlignment.objects.create(
        source_edition=source,
        target_edition=target,
        source_block=source_blocks[0],
        target_block=target_blocks[0],
        group_id=group_id,
        confidence=0.61,
        strategy="multilingual-embedding-monotonic-v2",
    )
    warning = QAWarning.objects.create(
        edition=target,
        block=target_blocks[0],
        code="alignment_low_confidence",
        severity=QAWarning.Severity.WARNING,
        message="Review this alignment group.",
    )
    return target, source_blocks, target_blocks, group_id, warning


def test_alignment_review_shows_pairs_gaps_and_accepts_group(client) -> None:
    target, _, _, group_id, warning = alignment_review_records()
    staff = get_user_model().objects.create_user(username="aligner", password="safe-password")
    staff.is_staff = True
    staff.save(update_fields=["is_staff"])
    client.force_login(staff)

    page = client.get(reverse("catalog:alignment-review", args=[target.id]))

    content = page.content.decode()
    assert page.status_code == 200
    assert "First source." in content
    assert "Première cible." in content
    assert "Second source." in content
    assert "Deuxième cible." in content
    assert "61%" in content
    assert "Unmatched blocks" in content

    response = client.post(
        reverse("catalog:accept-alignment-group", args=[target.id, group_id]),
        {"chapter": "1", "notes": "Meaning and paragraph boundaries match."},
    )

    assert response.status_code == 302
    warning.refresh_from_db()
    review = AlignmentGroupReview.objects.get(target_edition=target, group_id=group_id)
    assert warning.resolved_by == staff
    assert review.decision == AlignmentGroupReview.Decision.ACCEPTED
    assert review.notes == "Meaning and paragraph boundaries match."


def test_alignment_review_can_accept_a_chapter(client) -> None:
    target, _, _, group_id, warning = alignment_review_records()
    staff = get_user_model().objects.create_user(
        username="chapter-reviewer", password="safe-password"
    )
    staff.is_staff = True
    staff.save(update_fields=["is_staff"])
    client.force_login(staff)

    response = client.post(
        reverse("catalog:accept-alignment-chapter", args=[target.id]),
        {"chapter": "1", "notes": "Compared every visible group in this chapter."},
    )

    assert response.status_code == 302
    warning.refresh_from_db()
    review = AlignmentGroupReview.objects.get(target_edition=target, group_id=group_id)
    assert warning.resolved_at is not None
    assert review.reviewer == staff
    assert review.notes == "Compared every visible group in this chapter."


def test_alignment_review_can_replace_groups_with_manual_pairing(client) -> None:
    target, source_blocks, target_blocks, _, _ = alignment_review_records()
    BlockAlignment.objects.create(
        source_edition=target.source_edition,
        target_edition=target,
        source_block=source_blocks[1],
        target_block=target_blocks[1],
        group_id=uuid.uuid4(),
        confidence=0.8,
        strategy="multilingual-embedding-monotonic-v2",
    )
    staff = get_user_model().objects.create_user(username="repairer", password="safe-password")
    staff.is_staff = True
    staff.save(update_fields=["is_staff"])
    client.force_login(staff)

    response = client.post(
        reverse("catalog:repair-alignment", args=[target.id]),
        {
            "chapter": "1",
            "source_blocks": [str(block.id) for block in source_blocks],
            "target_blocks": [str(target_blocks[0].id)],
            "notes": "Two source paragraphs map to one French paragraph.",
        },
    )

    assert response.status_code == 302
    alignments = list(BlockAlignment.objects.filter(target_edition=target))
    assert len(alignments) == 2
    assert {alignment.source_block for alignment in alignments} == set(source_blocks)
    assert {alignment.target_block for alignment in alignments} == {target_blocks[0]}
    assert {alignment.strategy for alignment in alignments} == {"human-reviewed-v1"}
    review = AlignmentGroupReview.objects.get(target_edition=target)
    assert review.decision == AlignmentGroupReview.Decision.REPAIRED


def test_alignment_review_edits_target_text_with_audit(
    client, monkeypatch, django_capture_on_commit_callbacks
) -> None:
    target, _, target_blocks, _, _ = alignment_review_records()
    target.word_count = 4
    target.save(update_fields=["word_count"])
    staff = get_user_model().objects.create_user(username="editor", password="safe-password")
    staff.is_staff = True
    staff.save(update_fields=["is_staff"])
    queued: list[str] = []
    monkeypatch.setattr(
        "almonium_book_processor.catalog.tasks.split_edition_sentences.delay",
        lambda edition_id: queued.append(edition_id),
    )
    client.force_login(staff)

    with django_capture_on_commit_callbacks(execute=True):
        response = client.post(
            reverse("catalog:edit-alignment-target", args=[target.id, target_blocks[0].id]),
            {
                "chapter": "1",
                "text": "Première cible corrigée.",
                "notes": "Corrected the translation punctuation.",
            },
        )

    assert response.status_code == 302
    target_blocks[0].refresh_from_db()
    target.refresh_from_db()
    revision = ContentBlockRevision.objects.get(edition=target)
    assert target_blocks[0].text == "Première cible corrigée."
    assert target_blocks[0].sentences == []
    assert revision.previous_text == "Première cible."
    assert revision.revised_text == "Première cible corrigée."
    assert revision.editor == staff
    assert target.word_count == 5
    assert queued == [str(target.id)]


def test_schema_one_json_import_migrates_and_uses_uuid_identity() -> None:
    artifact = BookArtifact(
        processor_version="0.1.0",
        edition=EditionMetadata(
            edition_slug="shelley-frankenstein-en-orig",
            work_slug="shelley-frankenstein",
            title="Frankenstein",
            author="Mary Shelley",
            language="en",
            source=SourceMetadata(
                format="legacy_html",
                path="books/1.html",
                sha256="a" * 64,
            ),
        ),
        blocks=[
            ArtifactBlock(
                edition_slug="shelley-frankenstein-en-orig",
                block_id="c1.p1",
                chapter=1,
                seq=1,
                type=BlockType.PARAGRAPH,
                text="It was on a dreary night of November.",
            )
        ],
    )
    payload = artifact.model_dump(mode="json")
    payload["schema_version"] = 1
    payload["edition"]["edition_id"] = payload["edition"].pop("edition_slug")
    payload["edition"]["work_id"] = payload["edition"].pop("work_slug")
    for block in payload["blocks"]:
        block["schema_version"] = 1
        block["edition_id"] = block.pop("edition_slug")
    upload = BytesIO(json.dumps(payload).encode())

    edition = import_legacy_artifact(upload)

    assert str(edition.id) != "1"
    assert edition.status == Edition.Status.READY
    assert ContentBlock.objects.get(edition=edition).block_id == "c1.p1"


def test_dashboard_requires_staff_login(client) -> None:
    response = client.get(reverse("catalog:dashboard"))
    assert response.status_code == 302
    assert response.url.startswith("/admin/login/")

    staff = get_user_model().objects.create_user(username="editor", password="safe-test-password")
    staff.is_staff = True
    staff.save(update_fields=["is_staff"])
    client.force_login(staff)
    assert client.get(reverse("catalog:dashboard")).status_code == 200


def test_public_catalogue_and_user_imports_are_separate(client) -> None:
    staff = get_user_model().objects.create_user(username="operator", password="safe-test-password")
    staff.is_staff = True
    staff.save(update_fields=["is_staff"])
    public_work = Work.objects.create(
        slug="public-list-work",
        title="Public List Work",
        author="Ada Author",
        original_language="en",
    )
    private_work = Work.objects.create(
        slug="private-list-work",
        title="Private List Work",
        author="Private Author",
        original_language="en",
        visibility=Work.Visibility.PRIVATE,
        owner_id=uuid.uuid4(),
        owner_label="private-reader",
    )
    Edition.objects.create(
        slug="public-list-work-en",
        work=public_work,
        title="Public List Work",
        author="Ada Author",
        language="en",
        status=Edition.Status.READY,
    )
    private_edition = Edition.objects.create(
        slug="private-list-work-en",
        work=private_work,
        title="Private List Work",
        author="Private Author",
        language="en",
        status=Edition.Status.READY,
    )
    client.force_login(staff)

    public_page = client.get(reverse("catalog:dashboard")).content.decode()
    imports_page = client.get(reverse("catalog:private-imports")).content.decode()
    detail_page = client.get(
        reverse("catalog:edition-detail", args=[private_edition.id])
    ).content.decode()

    assert "Public List Work" in public_page
    assert "Private List Work" not in public_page
    assert "Private List Work" in imports_page
    assert str(private_work.owner_id) in imports_page
    assert "@private-reader" in imports_page
    assert "Available" in detail_page
    assert "Publish to Almonium" not in detail_page


def test_staff_can_release_repaired_private_content(
    client, monkeypatch, django_capture_on_commit_callbacks
) -> None:
    staff = get_user_model().objects.create_user(username="repairer", password="safe-test-password")
    staff.is_staff = True
    staff.save(update_fields=["is_staff"])
    work = Work.objects.create(
        slug="private-repair-work",
        title="Private Repair Work",
        author="Private Author",
        original_language="en",
        visibility=Work.Visibility.PRIVATE,
        owner_id=uuid.uuid4(),
    )
    edition = Edition.objects.create(
        slug="private-repair-work-en",
        work=work,
        title="Private Repair Work",
        author="Private Author",
        language="en",
        source_sha256="c" * 64,
        status=Edition.Status.FAILED,
    )
    chapter = Chapter.objects.create(edition=edition, sequence=1, title="One")
    ContentBlock.objects.create(
        edition=edition,
        chapter=chapter,
        block_id="c1.p1",
        sequence=1,
        block_type=ContentBlock.BlockType.PARAGRAPH,
        text="Repaired content.",
    )
    queued: list[str] = []
    monkeypatch.setattr(
        "almonium_book_processor.catalog.tasks.report_private_import_available.delay",
        lambda edition_id: queued.append(edition_id),
    )
    client.force_login(staff)

    with django_capture_on_commit_callbacks(execute=True):
        response = client.post(
            reverse("catalog:release-private-import", args=[edition.id]),
            {"notes": "Checked the repaired paragraph."},
        )

    assert response.status_code == 302
    edition.refresh_from_db()
    assert edition.status == Edition.Status.READY
    assert edition.review_decisions.get().notes == "Checked the repaired paragraph."
    assert queued == [str(edition.id)]


def test_staff_can_retry_failed_legacy_edition(client, monkeypatch) -> None:
    staff = get_user_model().objects.create_user(username="retryer", password="safe-password")
    staff.is_staff = True
    staff.save(update_fields=["is_staff"])
    work = Work.objects.create(
        slug="retry-work",
        title="Retry Work",
        author="Retry Author",
        original_language="en",
    )
    edition = Edition.objects.create(
        slug="retry-work-fr",
        work=work,
        title="Retry Work",
        author="Retry Author",
        language="fr",
        source_sha256="d" * 64,
        status=Edition.Status.FAILED,
    )
    chapter = Chapter.objects.create(edition=edition, sequence=1, title="One")
    ContentBlock.objects.create(
        edition=edition,
        chapter=chapter,
        block_id="c1.p1",
        sequence=1,
        block_type=ContentBlock.BlockType.PARAGRAPH,
        text="Contenu normalisé.",
    )
    queued: list[str] = []
    monkeypatch.setattr(
        "almonium_book_processor.catalog.tasks.process_normalized_edition.delay",
        lambda edition_id: queued.append(edition_id),
    )
    client.force_login(staff)

    detail = client.get(reverse("catalog:edition-detail", args=[edition.id]))
    response = client.post(reverse("catalog:retry-edition", args=[edition.id]))

    assert detail.status_code == 200
    assert "Retry processing" in detail.content.decode()
    assert response.status_code == 302
    assert queued == [str(edition.id)]


def test_public_api_exposes_only_published_editions(client) -> None:
    work = Work.objects.create(
        slug="public-work",
        title="Public Work",
        author="Ada Author",
        original_language="en",
    )
    Edition.objects.create(
        slug="public-work-en-draft",
        work=work,
        title="Draft",
        author="Ada Author",
        language="en",
        status=Edition.Status.DRAFT,
    )
    Edition.objects.create(
        slug="public-work-en-orig",
        work=work,
        title="Published",
        author="Ada Author",
        language="en",
        status=Edition.Status.PUBLISHED,
    )

    response = client.get("/api/v1/public/editions/")

    assert response.status_code == 200
    assert [item["slug"] for item in response.json()] == ["public-work-en-orig"]


def test_public_parallel_api_exposes_reviewed_alignment(client) -> None:
    work = Work.objects.create(
        slug="parallel-work",
        title="Parallel Work",
        author="Ada Author",
        original_language="en",
        publication_year=1912,
    )
    source = Edition.objects.create(
        slug="parallel-work-en-orig",
        work=work,
        title="Parallel Work",
        author="Ada Author",
        language="en",
        status=Edition.Status.PUBLISHED,
    )
    target = Edition.objects.create(
        slug="parallel-work-de-human",
        work=work,
        source_edition=source,
        title="Paralleles Werk",
        author="Ada Author",
        language="de",
        edition_type=Edition.EditionType.HUMAN_TRANSLATION,
        status=Edition.Status.PUBLISHED,
    )
    source_chapter = Chapter.objects.create(edition=source, sequence=1)
    target_chapter = Chapter.objects.create(edition=target, sequence=1)
    source_block = ContentBlock.objects.create(
        edition=source,
        chapter=source_chapter,
        block_id="c1.p1",
        sequence=1,
        block_type=ContentBlock.BlockType.PARAGRAPH,
        text="Original text.",
    )
    target_block = ContentBlock.objects.create(
        edition=target,
        chapter=target_chapter,
        block_id="c1.p1",
        sequence=1,
        block_type=ContentBlock.BlockType.PARAGRAPH,
        text="Übersetzter Text.",
    )
    BlockAlignment.objects.create(
        source_edition=source,
        target_edition=target,
        source_block=source_block,
        target_block=target_block,
        confidence=0.98,
        strategy="test",
    )

    response = client.get(
        "/api/v1/public/editions/parallel-work-de-human/parallel/parallel-work-en-orig/"
    )

    assert response.status_code == 200
    assert response.json() == {
        "primary_language": "de",
        "secondary_language": "en",
        "blocks": [
            {
                "chapter": 1,
                "chapter_title": "",
                "sequence": 1,
                "block_type": "paragraph",
                "primary_text": "Übersetzter Text.",
                "secondary_text": "Original text.",
            }
        ],
    }


def test_offline_sentence_and_alignment_tasks(monkeypatch) -> None:
    work = Work.objects.create(
        slug="aligned-work",
        title="Aligned Work",
        author="Ada Author",
        original_language="en",
    )
    source = Edition.objects.create(
        slug="aligned-work-en-orig",
        work=work,
        title="Aligned Work",
        author="Ada Author",
        language="en",
        source_sha256="a" * 64,
    )
    target = Edition.objects.create(
        slug="aligned-work-fr-human",
        work=work,
        source_edition=source,
        title="Œuvre alignée",
        author="Ada Author",
        language="fr",
        edition_type=Edition.EditionType.HUMAN_TRANSLATION,
        source_sha256="b" * 64,
    )
    source_chapter = Chapter.objects.create(edition=source, sequence=1)
    target_chapter = Chapter.objects.create(edition=target, sequence=1)
    source_block = ContentBlock.objects.create(
        edition=source,
        chapter=source_chapter,
        block_id="c1.p1",
        sequence=1,
        block_type=ContentBlock.BlockType.PARAGRAPH,
        text="One. Two.",
    )
    target_block = ContentBlock.objects.create(
        edition=target,
        chapter=target_chapter,
        block_id="c1.p1",
        sequence=1,
        block_type=ContentBlock.BlockType.PARAGRAPH,
        text="Un. Deux.",
    )
    monkeypatch.setattr(
        "almonium_book_processor.catalog.tasks.split_sentences",
        lambda text, language: ["One.", "Two."],
    )
    monkeypatch.setattr(
        "almonium_book_processor.catalog.tasks.embed_texts",
        lambda texts: [[1.0, 0.0] for _ in texts],
    )

    split_edition_sentences.run(str(source.id))
    align_edition_to_source.run(str(target.id))

    source_block.refresh_from_db()
    assert source_block.sentences == [
        {"id": "c1.p1.s1", "start": 0, "end": 4},
        {"id": "c1.p1.s2", "start": 5, "end": 9},
    ]
    alignment = BlockAlignment.objects.get()
    assert alignment.source_block == source_block
    assert alignment.target_block == target_block
    assert alignment.confidence == pytest.approx(1.0)


def test_normalized_pipeline_groups_split_blocks_and_finishes_ready(monkeypatch) -> None:
    work = Work.objects.create(
        slug="split-alignment-work",
        title="Split Alignment Work",
        author="Ada Author",
        original_language="en",
    )
    source = Edition.objects.create(
        slug="split-alignment-work-en",
        work=work,
        title="Split Alignment Work",
        author="Ada Author",
        language="en",
        source_sha256="c" * 64,
        status=Edition.Status.READY,
    )
    target = Edition.objects.create(
        slug="split-alignment-work-fr",
        work=work,
        source_edition=source,
        title="Œuvre divisée",
        author="Ada Author",
        language="fr",
        edition_type=Edition.EditionType.HUMAN_TRANSLATION,
        source_sha256="d" * 64,
        status=Edition.Status.READY,
    )
    source_chapter = Chapter.objects.create(edition=source, sequence=1)
    target_chapter = Chapter.objects.create(edition=target, sequence=1)
    ContentBlock.objects.create(
        edition=source,
        chapter=source_chapter,
        block_id="c1.p1",
        sequence=1,
        block_type=ContentBlock.BlockType.PARAGRAPH,
        text="A source paragraph.",
    )
    for sequence, text in enumerate(("Première partie.", "Deuxième partie."), start=1):
        ContentBlock.objects.create(
            edition=target,
            chapter=target_chapter,
            block_id=f"c1.p{sequence}",
            sequence=sequence,
            block_type=ContentBlock.BlockType.PARAGRAPH,
            text=text,
        )
    monkeypatch.setattr(
        "almonium_book_processor.catalog.tasks.split_sentences",
        lambda text, language: [text],
    )
    monkeypatch.setattr(
        "almonium_book_processor.catalog.tasks.embed_texts",
        lambda texts: [[1.0, 0.0] for _ in texts],
    )

    process_normalized_edition.run(str(target.id))

    target.refresh_from_db()
    alignments = list(BlockAlignment.objects.order_by("target_block__sequence"))
    assert target.status == Edition.Status.READY
    assert len(alignments) == 2
    assert len({alignment.group_id for alignment in alignments}) == 1
    assert not target.warnings.exists()


def test_normalized_pipeline_routes_low_confidence_alignment_to_review(monkeypatch) -> None:
    work = Work.objects.create(
        slug="uncertain-work",
        title="Uncertain Work",
        author="Ada Author",
        original_language="en",
    )
    source = Edition.objects.create(
        slug="uncertain-work-en",
        work=work,
        title="Uncertain Work",
        author="Ada Author",
        language="en",
        source_sha256="e" * 64,
    )
    target = Edition.objects.create(
        slug="uncertain-work-fr",
        work=work,
        source_edition=source,
        title="Œuvre incertaine",
        author="Ada Author",
        language="fr",
        edition_type=Edition.EditionType.HUMAN_TRANSLATION,
        source_sha256="f" * 64,
    )
    source_chapter = Chapter.objects.create(edition=source, sequence=1)
    target_chapter = Chapter.objects.create(edition=target, sequence=1)
    ContentBlock.objects.create(
        edition=source,
        chapter=source_chapter,
        block_id="c1.p1",
        sequence=1,
        block_type=ContentBlock.BlockType.PARAGRAPH,
        text="Source text.",
    )
    ContentBlock.objects.create(
        edition=target,
        chapter=target_chapter,
        block_id="c1.p1",
        sequence=1,
        block_type=ContentBlock.BlockType.PARAGRAPH,
        text="Texte cible.",
    )
    vectors = iter(([[1.0, 0.0]], [[0.5, 0.8660254]]))
    monkeypatch.setattr(
        "almonium_book_processor.catalog.tasks.split_sentences",
        lambda text, language: [text],
    )
    monkeypatch.setattr(
        "almonium_book_processor.catalog.tasks.embed_texts",
        lambda texts: next(vectors),
    )

    process_normalized_edition.run(str(target.id))

    target.refresh_from_db()
    warning = target.warnings.get(code="alignment_low_confidence")
    assert target.status == Edition.Status.REVIEW
    assert warning.pipeline_run.stage == PipelineRun.Stage.ALIGN


def test_publication_requires_current_cheap_nlp() -> None:
    work = Work.objects.create(
        slug="publication-gate-work",
        title="Publication Gate Work",
        author="Ada Author",
        original_language="en",
        publication_year=1912,
    )
    edition = Edition.objects.create(
        slug="publication-gate-work-en",
        work=work,
        title="Publication Gate Work",
        author="Ada Author",
        language="en",
        cefr_level=Edition.CEFRLevel.B2,
        source_sha256="1" * 64,
        status=Edition.Status.READY,
    )

    with pytest.raises(ValueError, match="sentence splitting"):
        publish_edition.run(str(edition.id))
