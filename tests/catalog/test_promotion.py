from __future__ import annotations

import io
import json
import uuid
import zipfile

import pytest
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.test import Client
from django.urls import reverse
from django.utils import timezone
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from almonium_book_processor.catalog import promotion
from almonium_book_processor.catalog.models import (
    AlignmentGroupReview,
    BlockAlignment,
    Chapter,
    ChapterAlignment,
    ContentBlock,
    ContentBlockRevision,
    Edition,
    EditionArtifact,
    PipelineRun,
    PromotionTarget,
    QAWarning,
    ReviewDecision,
    TextQualityFinding,
    Work,
)
from almonium_book_processor.catalog.promotion import (
    BUNDLE_SCHEMA_VERSION,
    MANIFEST_NAME,
    PromotionError,
    bundle_hash,
    capabilities,
    compatibility_problem,
    export_bundle,
    import_bundle,
    promotion_blocker,
    promotion_chain,
)
from almonium_book_processor.catalog.tasks import promote_edition

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def media_root(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path / "media"


def make_user(username: str = "reviewer", *, staff: bool = False):
    user = get_user_model().objects.create_user(username, f"{username}@example.test", "pw")
    if staff:
        user.is_staff = True
        user.save(update_fields=["is_staff"])
    return user


def build_edition(
    *,
    slug: str,
    work: Work | None = None,
    source_edition: Edition | None = None,
    status: str = Edition.Status.READY,
    edition_type: str = Edition.EditionType.ORIGINAL,
    reviewer=None,
    with_file: bool = True,
) -> Edition:
    work = work or Work.objects.create(
        slug=f"work-{uuid.uuid4().hex[:8]}",
        title="Travelling Work",
        author="Ada Author",
        original_language="en",
        publication_year=1818,
        description="A work that goes places.",
    )
    edition = Edition.objects.create(
        slug=slug,
        work=work,
        source_edition=source_edition,
        title="Travelling Book",
        author="Ada Author",
        language="en" if source_edition is None else "uk",
        status=status,
        edition_type=edition_type,
        cefr_level=Edition.CEFRLevel.B2,
        word_count=42,
        source_sha256="a" * 64,
    )
    if with_file:
        edition.source_file.save("travelling.epub", ContentFile(b"epub bytes"), save=True)
    chapter = Chapter.objects.create(edition=edition, sequence=1, title="One")
    blocks = [
        ContentBlock.objects.create(
            edition=edition,
            chapter=chapter,
            block_id=f"b{index}",
            sequence=index,
            block_type="paragraph",
            text=f"Paragraph {index}.",
            sentences=[{"start": 0, "end": 12}],
            align_group=uuid.uuid4(),
        )
        for index in range(3)
    ]
    run = PipelineRun.objects.create(
        edition=edition,
        stage=PipelineRun.Stage.SENTENCES,
        status=PipelineRun.Status.SUCCEEDED,
        idempotency_key=f"{edition.id}:sentences",
        processor_version="0.2.0",
        input_hash="b" * 64,
        summary={"blocks": 3},
    )
    PipelineRun.objects.create(
        edition=edition,
        stage=PipelineRun.Stage.PUBLISH,
        status=PipelineRun.Status.SUCCEEDED,
        idempotency_key=f"{edition.id}:publish",
        processor_version="0.2.0",
        input_hash="c" * 64,
        summary={"almonium_book_id": str(uuid.uuid4())},
    )
    artifact = EditionArtifact.objects.create(
        edition=edition,
        chapter=chapter,
        pipeline_run=run,
        kind=EditionArtifact.Kind.LEXICAL_PROFILE,
        input_hash="d" * 64,
        processor_version="lexical-v1",
        payload={"total_tokens": 9, "block_ids": [str(block.id) for block in blocks]},
    )
    ContentBlockRevision.objects.create(
        edition=edition,
        block=blocks[0],
        stable_block_id="b0",
        editor=reviewer,
        previous_text="Paragraph 0",
        revised_text="Paragraph 0.",
        notes="Added the full stop.",
    )
    TextQualityFinding.objects.create(
        edition=edition,
        pipeline_run=run,
        artifact=artifact,
        block=blocks[1],
        stable_block_id="b1",
        input_hash="e" * 64,
        fingerprint="f" * 64,
        code="detached_initial",
        status=TextQualityFinding.Status.DISMISSED,
        confidence=0.9,
        message="Looks detached.",
        reviewed_by=reviewer,
        reviewed_at=timezone.now(),
    )
    QAWarning.objects.create(
        edition=edition,
        pipeline_run=run,
        block=blocks[2],
        code="alignment_low_confidence",
        message="Check this.",
        resolved_at=timezone.now(),
        resolved_by=reviewer,
    )
    ReviewDecision.objects.create(
        edition=edition,
        reviewer=reviewer,
        notes="Looks good.",
        source_sha256="a" * 64,
    )
    if source_edition is not None:
        source_blocks = list(source_edition.blocks.order_by("sequence"))
        source_chapter = source_edition.chapters.get()
        ChapterAlignment.objects.create(
            source_edition=source_edition,
            target_edition=edition,
            source_chapter=source_chapter,
            target_chapter=chapter,
            confidence=0.95,
            strategy="embedding",
        )
        for source_block, target_block in zip(source_blocks, blocks, strict=True):
            BlockAlignment.objects.create(
                source_edition=source_edition,
                target_edition=edition,
                source_block=source_block,
                target_block=target_block,
                confidence=0.9,
                strategy="embedding",
            )
        AlignmentGroupReview.objects.create(
            target_edition=edition,
            group_id=uuid.uuid4(),
            reviewer=reviewer,
            decision=AlignmentGroupReview.Decision.ACCEPTED,
            source_block_ids=[str(source_blocks[0].id)],
            target_block_ids=[str(blocks[0].id)],
        )
    return edition


def counts(edition_id) -> dict[str, int]:
    return {
        "chapters": Chapter.objects.filter(edition_id=edition_id).count(),
        "blocks": ContentBlock.objects.filter(edition_id=edition_id).count(),
        "runs": PipelineRun.objects.filter(edition_id=edition_id).count(),
        "artifacts": EditionArtifact.objects.filter(edition_id=edition_id).count(),
        "revisions": ContentBlockRevision.objects.filter(edition_id=edition_id).count(),
        "findings": TextQualityFinding.objects.filter(edition_id=edition_id).count(),
        "warnings": QAWarning.objects.filter(edition_id=edition_id).count(),
        "decisions": ReviewDecision.objects.filter(edition_id=edition_id).count(),
        "group_reviews": AlignmentGroupReview.objects.filter(target_edition_id=edition_id).count(),
        "chapter_alignments": ChapterAlignment.objects.filter(target_edition_id=edition_id).count(),
        "block_alignments": BlockAlignment.objects.filter(target_edition_id=edition_id).count(),
    }


def wipe(edition: Edition) -> None:
    """Forget the edition the way another environment never knew it."""

    work = edition.work
    edition.delete()
    if not work.editions.exists():
        work.delete()


def manifest_of(bundle: bytes) -> dict:
    with zipfile.ZipFile(io.BytesIO(bundle)) as archive:
        return json.loads(archive.read(MANIFEST_NAME))


def rebundle(manifest: dict, files: dict[str, bytes] | None = None) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(MANIFEST_NAME, json.dumps(manifest))
        for name, data in (files or {}).items():
            archive.writestr(name, data)
    return buffer.getvalue()


# --------------------------------------------------------------------------
# Export.


def test_the_chain_lists_sources_first_and_the_bundle_carries_them_all():
    reviewer = make_user()
    original = build_edition(slug="book-en", reviewer=reviewer)
    translation = build_edition(
        slug="book-uk",
        work=original.work,
        source_edition=original,
        edition_type=Edition.EditionType.MACHINE_TRANSLATION,
        reviewer=reviewer,
        with_file=False,
    )

    assert [item.slug for item in promotion_chain(translation)] == ["book-en", "book-uk"]
    manifest = manifest_of(export_bundle(translation))

    assert [section["edition"]["slug"] for section in manifest["editions"]] == [
        "book-en",
        "book-uk",
    ]
    assert manifest["bundle_schema_version"] == BUNDLE_SCHEMA_VERSION
    assert manifest["catalog_migration"] == promotion.catalog_migration()
    en, uk = manifest["editions"]
    assert en["edition"]["source_file"].endswith(".epub")
    assert uk["edition"]["source_file"] is None
    assert uk["block_alignments"][0]["source_edition_id"] == str(original.id)
    assert [run["stage"] for run in en["pipeline_runs"]] == ["sentences"], (
        "publication runs describe the origin's product API, not the edition"
    )
    assert en["block_revisions"][0]["editor_username"] == "reviewer"


def test_a_private_import_or_an_unreviewed_source_cannot_travel():
    private = build_edition(slug="private-book")
    private.work.visibility = Work.Visibility.PRIVATE
    private.work.save(update_fields=["visibility"])
    assert "never promoted" in promotion_blocker(private)

    draft_source = build_edition(slug="draft-en", status=Edition.Status.REVIEW)
    derived = build_edition(
        slug="derived-uk",
        work=draft_source.work,
        source_edition=draft_source,
        edition_type=Edition.EditionType.MACHINE_TRANSLATION,
    )
    assert promotion_blocker(derived) == (
        "Its source draft-en is needs review; only reviewed editions travel."
    )
    with pytest.raises(PromotionError):
        export_bundle(derived)


def test_the_same_content_bundles_to_the_same_hash():
    edition = build_edition(slug="stable-en")

    assert bundle_hash(export_bundle(edition)) == bundle_hash(export_bundle(edition))


# --------------------------------------------------------------------------
# Import.


def test_a_bundle_lands_with_the_same_ids_and_lands_again_as_a_no_op():
    reviewer = make_user()
    original = build_edition(slug="book-en", reviewer=reviewer, status=Edition.Status.PUBLISHED)
    translation = build_edition(
        slug="book-uk",
        work=original.work,
        source_edition=original,
        edition_type=Edition.EditionType.MACHINE_TRANSLATION,
        reviewer=reviewer,
        with_file=False,
    )
    original_id, translation_id = original.id, translation.id
    expected = {
        slug: counts(edition.id)
        for slug, edition in (("book-en", original), ("book-uk", translation))
    }
    block_created = ContentBlock.objects.filter(edition=original).earliest("created_at").created_at
    bundle = export_bundle(translation)
    wipe(translation)
    wipe(original)
    # The target knows the reviewer under the same name, but not the editor.
    reviewer.delete()
    make_user("reviewer")

    result = import_bundle(bundle, origin="laptop")

    assert result["imported"] == ["book-en", "book-uk"]
    assert result["skipped"] == []
    landed = Edition.objects.get(id=original_id)
    assert landed.slug == "book-en"
    assert landed.status == Edition.Status.READY, "publication is the target's own decision"
    assert landed.published_book_id is None
    assert landed.promoted_from == "laptop"
    assert landed.promotion_fingerprint
    assert landed.source_file.read() == b"epub bytes"
    landed_uk = Edition.objects.get(id=translation_id)
    assert landed_uk.source_edition_id == original_id
    assert not landed_uk.source_file
    for slug, edition_id in (("book-en", original_id), ("book-uk", translation_id)):
        got = counts(edition_id)
        assert got == {**expected[slug], "runs": expected[slug]["runs"] - 1}, slug
    assert ContentBlock.objects.filter(edition=landed).earliest("created_at").created_at == (
        block_created
    )
    revision = ContentBlockRevision.objects.get(edition=landed)
    assert revision.editor.get_username() == "reviewer"
    assert ReviewDecision.objects.get(edition=landed).reviewer.get_username() == "reviewer"
    artifact = EditionArtifact.objects.get(edition=landed)
    assert artifact.payload["block_ids"] == [
        str(block.id) for block in landed.blocks.order_by("sequence")
    ]
    assert not PipelineRun.objects.filter(stage=PipelineRun.Stage.PUBLISH).exists()

    again = import_bundle(bundle, origin="laptop")

    assert again["imported"] == []
    assert again["skipped"] == ["book-en", "book-uk"]


def test_a_changed_edition_replaces_what_the_last_promotion_left():
    original = build_edition(slug="book-en")
    first = export_bundle(original)
    import_bundle(first, origin="laptop")
    landed = Edition.objects.get(id=original.id)
    # The target published it and ran its own publication; both must survive.
    landed.status = Edition.Status.PUBLISHED
    landed.published_book_id = uuid.uuid4()
    landed.save(update_fields=["status", "published_book_id"])
    own_publish = PipelineRun.objects.create(
        edition=landed,
        stage=PipelineRun.Stage.PUBLISH,
        status=PipelineRun.Status.SUCCEEDED,
        idempotency_key=f"{landed.id}:publish:target",
        processor_version="0.2.0",
        input_hash="c" * 64,
    )

    block = original.blocks.get(block_id="b1")
    block.text = "Paragraph 1, corrected."
    block.save(update_fields=["text"])
    original.title = "Travelling Book, second edition"
    original.save(update_fields=["title"])
    second = export_bundle(original)
    assert bundle_hash(second) != bundle_hash(first)
    # Source and target share a database here, so a row only the target has
    # is added once the bundle is sealed.
    stale_block = ContentBlock.objects.create(
        edition=landed,
        chapter=landed.chapters.get(),
        block_id="b-target-only",
        sequence=99,
        block_type="paragraph",
        text="Only the target had this.",
    )

    result = import_bundle(second, origin="laptop")

    assert result["imported"] == ["book-en"]
    landed.refresh_from_db()
    assert landed.title == "Travelling Book, second edition"
    assert landed.status == Edition.Status.PUBLISHED
    assert landed.published_book_id is not None
    assert landed.blocks.get(block_id="b1").text == "Paragraph 1, corrected."
    assert not ContentBlock.objects.filter(id=stale_block.id).exists()
    assert PipelineRun.objects.filter(id=own_publish.id).exists()


def test_a_slug_held_by_a_different_edition_refuses_the_whole_bundle():
    original = build_edition(slug="book-en")
    original_id = original.id
    bundle = export_bundle(original)
    wipe(original)
    squatter = build_edition(slug="book-en")

    with pytest.raises(PromotionError, match="already uses the slug book-en"):
        import_bundle(bundle)

    assert Edition.objects.get(slug="book-en").id == squatter.id
    assert not Edition.objects.filter(id=original_id).exists()


def test_a_bundle_from_another_schema_is_refused_before_anything_is_written():
    original = build_edition(slug="book-en")
    manifest = manifest_of(export_bundle(original))
    wipe(original)

    with pytest.raises(PromotionError, match="Bundle schema 99"):
        import_bundle(rebundle({**manifest, "bundle_schema_version": 99}))
    with pytest.raises(PromotionError, match="catalog migration 0001_initial"):
        import_bundle(rebundle({**manifest, "catalog_migration": "0001_initial"}))
    with pytest.raises(PromotionError, match="not an edition bundle"):
        import_bundle(b"not a zip")
    assert not Edition.objects.exists()


def test_compatibility_needs_the_same_bundle_schema_and_catalog_migration():
    ours = capabilities()

    assert compatibility_problem(ours) == ""
    assert "bundle schema 0" in compatibility_problem({**ours, "bundle_schema_version": 0})
    assert "0001_initial" in compatibility_problem({**ours, "catalog_migration": "0001_initial"})


def test_capabilities_describe_what_this_environment_holds():
    original = build_edition(slug="book-en")
    original.promotion_fingerprint = "f" * 64
    original.save(update_fields=["promotion_fingerprint"])

    described = capabilities(["book-en", "missing"])

    assert described["bundle_schema_version"] == BUNDLE_SCHEMA_VERSION
    assert described["catalog_migration"] == promotion.catalog_migration()
    assert described["editions"] == {
        "book-en": {
            "id": str(original.id),
            "status": "ready",
            "source_sha256": "a" * 64,
            "promotion_fingerprint": "f" * 64,
        }
    }


# --------------------------------------------------------------------------
# The target's endpoints.


def test_the_endpoints_take_a_staff_token_only():
    make_user("outsider")
    outsider_token = Token.objects.create(user=make_user("outsider2"))
    staff_token = Token.objects.create(user=make_user("staff", staff=True))
    client = APIClient()

    assert client.get(reverse("promotion-capabilities")).status_code == 401
    client.credentials(HTTP_AUTHORIZATION=f"Token {outsider_token.key}")
    assert client.get(reverse("promotion-capabilities")).status_code == 403
    client.credentials(HTTP_AUTHORIZATION=f"Token {staff_token.key}")
    response = client.get(reverse("promotion-capabilities"), {"slug": ["book-en"]})

    assert response.status_code == 200
    assert response.json()["bundle_schema_version"] == BUNDLE_SCHEMA_VERSION


def test_the_import_endpoint_lands_the_bundle_and_queues_publication_in_order(monkeypatch):
    original = build_edition(slug="book-en")
    translation = build_edition(
        slug="book-uk",
        work=original.work,
        source_edition=original,
        edition_type=Edition.EditionType.MACHINE_TRANSLATION,
        with_file=False,
    )
    original_id, translation_id = original.id, translation.id
    bundle = export_bundle(translation)
    wipe(translation)
    wipe(original)
    queued: list[list[str]] = []

    class FakeChain:
        def __init__(self, *signatures):
            self.signatures = signatures

        def apply_async(self):
            queued.append([signature.args[0] for signature in self.signatures])

    monkeypatch.setattr("celery.chain", FakeChain)
    token = Token.objects.create(user=make_user("staff", staff=True))
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")

    response = client.post(
        reverse("promotion-import"),
        {"bundle": ContentFile(bundle, name="book-uk.zip"), "publish": "true"},
        format="multipart",
    )

    assert response.status_code == 200, response.content
    body = response.json()
    assert body["imported"] == ["book-en", "book-uk"]
    assert body["publish_queued"] == ["book-en", "book-uk"]
    assert queued == [[str(original_id), str(translation_id)]]
    assert Edition.objects.get(id=translation_id).source_edition_id == original_id


def test_the_import_endpoint_explains_a_refusal():
    token = Token.objects.create(user=make_user("staff", staff=True))
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")

    missing = client.post(reverse("promotion-import"), {}, format="multipart")
    garbage = client.post(
        reverse("promotion-import"),
        {"bundle": ContentFile(b"nope", name="x.zip")},
        format="multipart",
    )

    assert missing.status_code == 400
    assert missing.json() == {"message": "An edition bundle is required."}
    assert garbage.status_code == 400
    assert garbage.json() == {"message": "This is not an edition bundle."}


# --------------------------------------------------------------------------
# The source's page and task.


def test_the_page_offers_promotion_and_the_form_queues_a_run(monkeypatch):
    staff = make_user("staff", staff=True)
    edition = build_edition(slug="book-en")
    client = Client()
    client.force_login(staff)

    page = client.get(reverse("catalog:edition-detail", args=[edition.id]))
    assert page.status_code == 200
    assert b"No promotion targets are configured" in page.content

    target = PromotionTarget.objects.create(
        name="staging", base_url="https://staging.example.test", token="secret"
    )
    page = client.get(reverse("catalog:edition-detail", args=[edition.id]))
    assert b"staging \xc2\xb7 https://staging.example.test" in page.content
    assert b"Never promoted" in page.content

    queued: list[tuple] = []
    monkeypatch.setattr(
        "almonium_book_processor.catalog.views.promote_edition.delay",
        lambda run_id, publish: queued.append((run_id, publish)),
    )
    response = client.post(
        reverse("catalog:promote-edition", args=[edition.id]),
        {"target": str(target.id), "publish": "on"},
    )

    assert response.status_code == 302
    run = PipelineRun.objects.get(stage=PipelineRun.Stage.PROMOTE)
    assert run.edition_id == edition.id
    assert run.summary == {"target": "staging", "target_id": str(target.id), "publish": True}
    assert queued == [(str(run.id), True)]
    page = client.get(reverse("catalog:edition-detail", args=[edition.id]))
    assert b"Last: staging" in page.content


def test_the_form_refuses_a_blocked_edition_and_an_unknown_target(monkeypatch):
    staff = make_user("staff", staff=True)
    edition = build_edition(slug="book-en", status=Edition.Status.REVIEW)
    target = PromotionTarget.objects.create(
        name="staging", base_url="https://staging.example.test", token="secret"
    )
    client = Client()
    client.force_login(staff)
    monkeypatch.setattr(
        "almonium_book_processor.catalog.views.promote_edition.delay",
        lambda *args, **kwargs: pytest.fail("nothing should be queued"),
    )

    client.post(reverse("catalog:promote-edition", args=[edition.id]), {"target": str(target.id)})
    client.post(
        reverse("catalog:promote-edition", args=[edition.id]), {"target": str(uuid.uuid4())}
    )

    assert not PipelineRun.objects.filter(stage=PipelineRun.Stage.PROMOTE).exists()


class FakeClient:
    remote: dict = {}
    pushed: list[dict] = []
    fail_push: str = ""

    def __init__(self, target):
        self.target = target

    def capabilities(self, slugs):
        return {**capabilities(slugs), **self.remote}

    def push(self, bundle, *, file_name, publish):
        if self.fail_push:
            raise PromotionError(self.fail_push)
        self.pushed.append({"file_name": file_name, "publish": publish, "size": len(bundle)})
        return {"imported": ["book-en"], "skipped": [], "publish_queued": ["book-en"]}


def promotion_run(edition: Edition, target: PromotionTarget, *, publish=True) -> PipelineRun:
    return PipelineRun.objects.create(
        edition=edition,
        stage=PipelineRun.Stage.PROMOTE,
        processor_version="0.2.0",
        input_hash="",
        idempotency_key=f"{edition.id}:promote:{target.name}:{uuid.uuid4().hex}",
        summary={"target": target.name, "target_id": str(target.id), "publish": publish},
    )


@pytest.fixture
def fake_client(monkeypatch):
    FakeClient.remote = {}
    FakeClient.pushed = []
    FakeClient.fail_push = ""
    monkeypatch.setattr("almonium_book_processor.catalog.tasks.PromotionClient", FakeClient)
    return FakeClient


def test_the_task_checks_the_target_then_pushes_and_records_the_answer(fake_client):
    edition = build_edition(slug="book-en")
    target = PromotionTarget.objects.create(
        name="staging", base_url="https://staging.example.test", token="secret"
    )
    run = promotion_run(edition, target)

    promote_edition(str(run.id), publish=True)

    run.refresh_from_db()
    assert run.status == PipelineRun.Status.SUCCEEDED
    assert len(run.input_hash) == 64
    assert run.summary["result"]["imported"] == ["book-en"]
    assert run.summary["bundle_bytes"] == fake_client.pushed[0]["size"]
    assert fake_client.pushed[0] == {
        "file_name": "book-en.zip",
        "publish": True,
        "size": run.summary["bundle_bytes"],
    }
    assert run.summary_note == (
        "to staging · copied book-en · publication queued there for book-en"
    )


def test_the_task_refuses_a_target_on_another_build_without_sending_anything(fake_client):
    fake_client.remote = {"catalog_migration": "0001_initial"}
    edition = build_edition(slug="book-en")
    target = PromotionTarget.objects.create(
        name="staging", base_url="https://staging.example.test", token="secret"
    )
    run = promotion_run(edition, target)

    with pytest.raises(PromotionError):
        promote_edition(str(run.id), publish=False)

    run.refresh_from_db()
    assert run.status == PipelineRun.Status.FAILED
    assert "0001_initial" in run.error
    assert fake_client.pushed == []


def test_the_task_records_what_the_target_answered_when_it_refuses(fake_client):
    fake_client.fail_push = "Promotion to staging failed with HTTP 400 (slug taken)."
    edition = build_edition(slug="book-en")
    target = PromotionTarget.objects.create(
        name="staging", base_url="https://staging.example.test", token="secret"
    )
    run = promotion_run(edition, target)

    with pytest.raises(PromotionError):
        promote_edition(str(run.id), publish=False)

    run.refresh_from_db()
    assert run.status == PipelineRun.Status.FAILED
    assert run.error == "Promotion to staging failed with HTTP 400 (slug taken)."
