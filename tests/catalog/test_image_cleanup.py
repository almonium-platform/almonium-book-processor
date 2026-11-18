from uuid import uuid4

import pytest

from almonium_book_processor.catalog import chapter_analysis, chapter_projections
from almonium_book_processor.catalog.image_cleanup import REASON, _sentence_hash, clean_image_text
from almonium_book_processor.catalog.models import AIRun, ContentBlock, EditionArtifact, PipelineRun
from almonium_book_processor.catalog.offline_sentence_alignment import _digest, processor_version
from almonium_book_processor.catalog.parallel_content import inherited_pairs, pair_hash
from almonium_book_processor.processing.sentence_correspondence import VERSION
from tests.catalog.test_sentence_alignment import pair  # noqa: F401

pytestmark = pytest.mark.django_db


def _run(edition, stage, digest, *, version="test", **summary):
    return PipelineRun.objects.create(
        edition=edition,
        stage=stage,
        status=PipelineRun.Status.SUCCEEDED,
        idempotency_key=f"{stage}:{digest}",
        input_hash=digest,
        processor_version=version,
        summary=summary,
    )


def _image(edition, group, text):
    return ContentBlock.objects.create(
        edition=edition,
        chapter=edition.chapters.get(),
        block_id="c11.i2",
        sequence=2,
        align_group=group,
        block_type="image",
        text=text,
        source_ref="plate.jpg",
        sentences=[{"start": 0, "end": len(text)}],
        attributes={"alt": text},
    )


def test_cleanup_carries_alignment_without_changing_paid_or_prose_inputs(pair):  # noqa: F811
    original, target = pair
    group = uuid4()
    image = _image(original, group, "A plate.")
    translated = _image(target, group, "A translated plate.")
    rows = inherited_pairs(*pair)
    model = "sentence-transformers/LaBSE"
    run = _run(
        original,
        "align",
        _digest(rows),
        version=processor_version(model),
        secondary_id=str(target.pk),
        model=model,
        method=VERSION,
        total_blocks=2,
        completed_blocks=2,
        highlighted_groups=2,
        uncertain_groups=0,
        paragraph_fallback_blocks=0,
        fallback_reasons={},
        unmatched_sentences=0,
        embedding={"usd": "0.10"},
    )
    prose, old_image = [
        EditionArtifact.objects.create(
            edition=original,
            chapter=left.chapter,
            kind="sentence_alignment",
            input_hash=pair_hash(left, right),
            processor_version=run.processor_version,
            pipeline_run=run,
            payload={"groups": [{"primary": [0], "secondary": [0], "certain": True}]},
        )
        for left, right in rows
    ]
    before_paid = list(AIRun.objects.all().values())
    sentence_run = _run(original, "sentences", _sentence_hash(original))

    assert clean_image_text()["image-only alignments"] == 1
    image.refresh_from_db()
    assert image.text == "A plate."
    assert PipelineRun.objects.count() == 2

    stats = clean_image_text(apply=True)
    assert stats["image blocks"] == 2
    assert stats["sentence runs carried"] == stats["alignment runs carried"] == 1
    image.refresh_from_db()
    translated.refresh_from_db()
    assert image.source_ref == "plate.jpg"
    assert image.align_group == translated.align_group == group
    assert image.text == translated.text == ""
    assert image.sentences == translated.sentences == []
    assert translated.attributes["legacy_image_text"] == {
        "text": "A translated plate.",
        "sentences": [{"start": 0, "end": 19}],
    }
    rows = inherited_pairs(*pair)
    prose.refresh_from_db()
    assert prose.is_current and prose.input_hash == pair_hash(*rows[0])
    assert prose.pipeline_run_id == run.id
    old_image.refresh_from_db()
    assert not old_image.is_current and old_image.payload["groups"]
    current = EditionArtifact.objects.get(input_hash=pair_hash(*rows[1]))
    assert current.payload["groups"] == []
    assert current.pipeline_run.input_hash == _digest(rows)
    assert current.pipeline_run.summary["highlighted_groups"] == 1
    assert "embedding" not in current.pipeline_run.summary
    assert current.pipeline_run.summary["image_cleanup"]["from_run"] == str(run.id)
    archived_run = PipelineRun.objects.get(stage="sentences", input_hash=_sentence_hash(original))
    assert archived_run.summary["image_cleanup"]["from_run"] == str(sentence_run.id)
    assert list(AIRun.objects.all().values()) == before_paid
    assert clean_image_text(apply=True)["image blocks"] == 0


def test_cleanup_keeps_current_chapter_readings_with_explicit_provenance(pair):  # noqa: F811
    edition, _ = pair
    _image(edition, uuid4(), "Portrait of the author.")
    chapter = edition.chapters.get()
    spec = chapter_analysis.edition_spec(edition)
    plan = chapter_analysis.snapshot(edition, spec)
    earlier = _run(
        edition, "chapter_analysis", plan["hash"], version=spec["processor_version"], spec=spec
    )
    reading = {
        "chapter_hash": plan["chapters"][0]["hash"],
        "cefr_estimate": "B1",
        "complete": True,
        "whitespace_tokens_total": 6,
        "whitespace_tokens_analyzed": 6,
        "confidence_min": 0.85,
        "confidence_max": 0.9,
    }
    original_summary = EditionArtifact.objects.create(
        edition=edition,
        chapter=chapter,
        kind="chapter_summary",
        pipeline_run=earlier,
        input_hash="summary",
        payload={**reading, "sections": []},
    )
    EditionArtifact.objects.create(
        edition=edition,
        chapter=chapter,
        kind="difficulty",
        pipeline_run=earlier,
        input_hash="difficulty",
        payload=reading,
    )
    EditionArtifact.objects.create(
        edition=edition,
        kind="difficulty",
        pipeline_run=earlier,
        input_hash="book",
        payload={"analysis_input_hash": plan["hash"]},
    )

    assert clean_image_text(apply=True)["analyses carried"] == 1
    context = chapter_analysis.analysis_context(edition)
    assert context["projection_state"] == "complete"
    carried = context["chapter_analysis_run"]
    assert carried.pk != earlier.pk
    assert context["book_difficulty"]["cefr_estimate"] == "B1"
    assert context["book_difficulty"]["image_cleanup"] == {
        "reason": REASON,
        "from_run": str(earlier.pk),
    }
    assert context["chapter_projections"][0]["summary"]["sections"] == []
    original_summary.refresh_from_db()
    assert not original_summary.is_current
    assert original_summary.payload["chapter_hash"] == plan["chapters"][0]["hash"]
    assert not AIRun.objects.exists()
    # A promotion bundle includes the current projections and omits retired rows.
    earlier.artifacts.all().delete()
    chapter_projections.refresh_projections(str(carried.pk))
    assert chapter_analysis.analysis_context(edition)["projection_state"] == "complete"
