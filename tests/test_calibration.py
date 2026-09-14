from __future__ import annotations

import io
import json
from pathlib import Path

import pytest
from django.core.management import call_command
from pydantic import ValidationError

from almonium_book_processor.ai.chapter_analysis import ChapterAnalysis
from almonium_book_processor.catalog.chapter_analysis import _verify_citations
from almonium_book_processor.processing.calibration import (
    FixtureSet,
    Prediction,
    PredictionSet,
    ReferenceRating,
    compare,
)

FIXTURES = Path(__file__).parent / "fixtures" / "calibration" / "difficulty-v1.json"


def fixture_set():
    return FixtureSet.model_validate_json(FIXTURES.read_text(encoding="utf-8"))


def prediction(sample, **kwargs):
    return Prediction.model_validate(
        {
            "sample_id": sample.id,
            "input_hash": sample.input_hash,
            "provider": "fake",
            "model": "fixture-model",
            "prompt_version": "2",
            "processor_version": "chapter-analysis-v2",
            "status": "succeeded",
            "cefr": "B2",
            **kwargs,
        }
    )


def test_seed_matrix_has_twelve_unrated_synthetic_samples():
    fixtures = fixture_set()
    assert len(fixtures.samples) == 12
    assert {(s.language, s.category) for s in fixtures.samples} == {
        (lang, category)
        for lang in ("en", "de", "uk")
        for category in ("letter", "dialogue", "archaic", "contemporary")
    }
    assert all(s.reference is None and s.source_kind == "synthetic" for s in fixtures.samples)
    assert len({s.input_hash for s in fixtures.samples}) == 12


@pytest.mark.parametrize("sample", fixture_set().samples, ids=lambda s: s.id)
def test_multilingual_fixture_citations_round_trip_exact_source_spans(sample):
    # B2 is an arbitrary fake-provider output here, never a reference rating.
    quote = sample.blocks[0].text[:60]
    result = ChapterAnalysis.model_validate(
        {
            "cefr_estimate": "B2",
            "confidence": 0.5,
            "archaism_score": 0.5,
            "modernisation_would_help": False,
            "evidence": [
                {
                    "block_id": sample.blocks[0].block_id,
                    "quote": quote,
                    "dimension": "syntax",
                    "explanation": "Fixture-only evidence.",
                }
            ],
            "spoiler_free_description": "Fixture description",
            "recap": "Fixture recap",
            "hard_words": [],
            "themes": [],
            "characters": [],
            "setting": "",
            "content_flags": [],
        }
    )
    validated, spans, notes = _verify_citations(
        result,
        {"blocks": [b.model_dump() for b in sample.blocks]},
    )
    span = spans[0]
    assert sample.blocks[0].text[span["start"] : span["end"]] == validated.evidence[0].quote
    assert notes == []


def test_unrated_predictions_cannot_produce_accuracy_metrics():
    fixtures = fixture_set()
    report = compare(
        fixtures, PredictionSet(schema_version=1, predictions=[prediction(fixtures.samples[0])])
    )
    group = report["configurations"][0]
    assert report["rated_samples"] == 0
    assert group["scored"] == 0
    assert group["exact_agreement"] is None
    assert group["mean_absolute_band_error"] is None
    assert len(group["missing_sample_ids"]) == 11
    assert group["unknown_cost_count"] == group["unknown_token_usage"] == 1


def test_scoring_reports_disagreement_and_retains_failed_attempt_cost():
    fixtures = fixture_set()
    for sample in fixtures.samples[:2]:
        sample.reference = ReferenceRating(
            cefr="C2",
            reviewer="Unit-test reviewer (not real calibration)",
            rationale="Test-only reference",
            reviewed_on="2026-09-14",
        )
    rows = [
        prediction(fixtures.samples[0], cefr="B2", estimated_cost_usd="0.02"),
        prediction(fixtures.samples[1], cefr="C2", estimated_cost_usd="0.03"),
        prediction(fixtures.samples[2], status="failed", cefr=None, estimated_cost_usd="0.01"),
    ]
    group = compare(fixtures, PredictionSet(schema_version=1, predictions=rows))["configurations"][
        0
    ]
    assert group["scored"] == 2
    assert group["failed"] == 1
    assert group["exact_agreement"] == 0.5
    assert group["mean_absolute_band_error"] == 1
    assert group["review_sample_ids"] == [fixtures.samples[0].id]
    assert group["reported_estimated_cost_usd"] == "0.06"


def test_different_model_and_prompt_versions_are_not_pooled():
    fixtures = fixture_set()
    sample = fixtures.samples[0]
    rows = [
        prediction(sample),
        prediction(sample, model="another"),
        prediction(sample, prompt_version="3"),
    ]
    report = compare(fixtures, PredictionSet(schema_version=1, predictions=rows))
    assert len(report["configurations"]) == 3
    assert all(g["submitted"] == 1 for g in report["configurations"])


def test_changed_text_rejects_stale_prediction_but_review_does_not_change_hash():
    fixtures = fixture_set()
    sample = fixtures.samples[0]
    saved = prediction(sample)
    sample.reference = ReferenceRating(
        cefr="B1",
        reviewer="Test-only",
        rationale="Synthetic unit test",
        reviewed_on="2026-09-14",
    )
    assert sample.input_hash == saved.input_hash
    sample.blocks[0].text += " "
    with pytest.raises(ValueError, match="Stale input hash"):
        compare(fixtures, PredictionSet(schema_version=1, predictions=[saved]))


def test_duplicate_predictions_cannot_inflate_coverage():
    fixtures = fixture_set()
    row = prediction(fixtures.samples[0])
    with pytest.raises(ValueError, match="Duplicate prediction"):
        compare(fixtures, PredictionSet(schema_version=1, predictions=[row, row]))


def test_failed_prediction_cannot_sneak_a_level_into_scores():
    with pytest.raises(ValidationError):
        prediction(fixture_set().samples[0], status="failed", cefr="C2")


def test_references_require_real_review_metadata_fields():
    with pytest.raises(ValidationError):
        ReferenceRating(cefr="B2", reviewer=" ", rationale=" ", reviewed_on="2026-99-99")


def test_command_is_read_only_and_works_without_an_api_key(settings):
    settings.OPENAI_API_KEY = ""
    stream = io.StringIO()
    call_command("check_calibration", str(FIXTURES), stdout=stream)
    report = json.loads(stream.getvalue())
    assert report["samples"] == 12
    assert report["rated_samples"] == 0
    assert report["configurations"] == []
