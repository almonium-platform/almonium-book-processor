from __future__ import annotations

from io import BytesIO

import pytest
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from ebooklib import epub

from almonium_book_processor.catalog.models import (
    BlockAlignment,
    Chapter,
    ContentBlock,
    Edition,
    PipelineRun,
    QAWarning,
    ReviewDecision,
    Work,
)
from almonium_book_processor.catalog.services import import_legacy_artifact, persist_artifact
from almonium_book_processor.catalog.tasks import (
    align_edition_to_source,
    process_source_edition,
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
    assert "Complete review" in page.content.decode()
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


def test_migrated_json_import_uses_uuid_identity() -> None:
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
    upload = BytesIO(artifact.model_dump_json().encode())

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
