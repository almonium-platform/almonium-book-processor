"""Offline difficulty-fixture validation and comparison; no provider or database access."""

from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Level = Literal["A1", "A2", "B1", "B2", "C1", "C2"]
LEVELS = ("A1", "A2", "B1", "B2", "C1", "C2")


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class ReferenceRating(StrictModel):
    cefr: Level
    reviewer: str = Field(min_length=1)
    rationale: str = Field(min_length=1)
    reviewed_on: date

    @model_validator(mode="after")
    def nonblank_review(self):
        if not self.reviewer.strip() or not self.rationale.strip():
            raise ValueError("Reference ratings require a named reviewer and rationale.")
        return self


class FixtureBlock(StrictModel):
    block_id: str = Field(min_length=1)
    text: str = Field(min_length=1)


class CalibrationSample(StrictModel):
    id: str = Field(min_length=1)
    language: Literal["en", "de", "uk"]
    category: Literal["letter", "dialogue", "archaic", "contemporary"]
    source_kind: Literal["synthetic", "catalog_excerpt"]
    source_note: str = Field(min_length=1)
    blocks: list[FixtureBlock] = Field(min_length=1)
    reference: ReferenceRating | None

    @model_validator(mode="after")
    def validate_blocks(self):
        ids = [b.block_id for b in self.blocks]
        if len(ids) != len(set(ids)):
            raise ValueError("Block IDs must be unique within a sample.")
        if any(not b.text.strip() for b in self.blocks):
            raise ValueError("Fixture text must not be blank.")
        return self

    @property
    def input_hash(self) -> str:
        # Ratings and display IDs are excluded; language, order, spelling and
        # block boundaries are part of the assessed input. No normalization.
        payload = [self.language, [b.model_dump() for b in self.blocks]]
        return hashlib.sha256(
            json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode()
        ).hexdigest()


class FixtureSet(StrictModel):
    schema_version: Literal[1]
    samples: list[CalibrationSample] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_samples(self):
        ids = [s.id for s in self.samples]
        if len(ids) != len(set(ids)):
            raise ValueError("Sample IDs must be unique.")
        return self


class Prediction(StrictModel):
    sample_id: str
    input_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    provider: str = Field(min_length=1)
    model: str = Field(min_length=1)
    prompt_version: str = Field(min_length=1)
    processor_version: str = Field(min_length=1)
    status: Literal["succeeded", "failed"]
    cefr: Level | None
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    estimated_cost_usd: Decimal | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def result_matches_status(self):
        if (self.status == "succeeded") != (self.cefr is not None):
            raise ValueError("Only successful predictions must have a CEFR estimate.")
        return self


class PredictionSet(StrictModel):
    schema_version: Literal[1]
    predictions: list[Prediction]


def compare(fixtures: FixtureSet, predictions: PredictionSet) -> dict:
    samples = {s.id: s for s in fixtures.samples}
    groups = defaultdict(list)
    seen = set()
    for prediction in predictions.predictions:
        sample = samples.get(prediction.sample_id)
        if sample is None:
            raise ValueError(f"Unknown sample: {prediction.sample_id}")
        if prediction.input_hash != sample.input_hash:
            raise ValueError(f"Stale input hash for sample: {sample.id}")
        configuration = (
            prediction.provider,
            prediction.model,
            prediction.prompt_version,
            prediction.processor_version,
        )
        key = (configuration, sample.id)
        if key in seen:
            raise ValueError("Duplicate prediction for the same sample and configuration.")
        seen.add(key)
        groups[configuration].append(prediction)
    reports = []
    for configuration, rows in sorted(groups.items()):
        scored = []
        for row in rows:
            sample = samples[row.sample_id]
            if row.status == "succeeded" and sample.reference:
                scored.append(
                    {
                        "sample_id": sample.id,
                        "language": sample.language,
                        "category": sample.category,
                        "reference": sample.reference.cefr,
                        "prediction": row.cefr,
                        "band_error": abs(
                            LEVELS.index(row.cefr) - LEVELS.index(sample.reference.cefr)
                        ),
                    }
                )
        reports.append(
            {
                "provider": configuration[0],
                "model": configuration[1],
                "prompt_version": configuration[2],
                "processor_version": configuration[3],
                "expected": len(samples),
                "submitted": len(rows),
                "succeeded": sum(r.status == "succeeded" for r in rows),
                "failed": sum(r.status == "failed" for r in rows),
                "missing_sample_ids": sorted(set(samples) - {r.sample_id for r in rows}),
                "scored": len(scored),
                "exact_agreement": sum(r["band_error"] == 0 for r in scored) / len(scored)
                if scored
                else None,
                "within_one_band": sum(r["band_error"] <= 1 for r in scored) / len(scored)
                if scored
                else None,
                "mean_absolute_band_error": sum(r["band_error"] for r in scored) / len(scored)
                if scored
                else None,
                "review_sample_ids": [r["sample_id"] for r in scored if r["band_error"] >= 2],
                "comparisons": scored,
                "reported_input_tokens": sum(r.input_tokens or 0 for r in rows),
                "reported_output_tokens": sum(r.output_tokens or 0 for r in rows),
                "unknown_token_usage": sum(
                    r.input_tokens is None or r.output_tokens is None for r in rows
                ),
                "reported_estimated_cost_usd": str(
                    sum((r.estimated_cost_usd or Decimal(0) for r in rows), Decimal(0))
                ),
                "unknown_cost_count": sum(r.estimated_cost_usd is None for r in rows),
            }
        )
    return {
        "schema_version": 1,
        "samples": len(samples),
        "rated_samples": sum(s.reference is not None for s in samples.values()),
        "unrated_sample_ids": [s.id for s in samples.values() if s.reference is None],
        "coverage": dict(
            sorted(Counter(f"{s.language}/{s.category}" for s in samples.values()).items())
        ),
        "fixture_inputs": {s.id: s.input_hash for s in samples.values()},
        "configurations": reports,
    }
