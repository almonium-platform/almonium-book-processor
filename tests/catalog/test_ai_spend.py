from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from almonium_book_processor.catalog.models import (
    AIRun,
    Edition,
    ModelConfiguration,
    PromptTemplate,
    Work,
)
from almonium_book_processor.catalog.spend import ai_spend

pytestmark = pytest.mark.django_db

SECRET = "test-shared-secret"


def edition() -> Edition:
    work = Work.objects.create(
        slug="spend-work", title="Spend", author="Ada", original_language="en"
    )
    return Edition.objects.create(
        slug="spend-work-en",
        work=work,
        title=work.title,
        author=work.author,
        language="en",
        source_sha256="c" * 64,
    )


def run(
    target: Edition,
    *,
    purpose: str,
    model: str,
    input_tokens: int,
    output_tokens: int,
    cost: str | None,
    status: str = AIRun.Status.SUCCEEDED,
    created_at=None,
) -> AIRun:
    configuration, _ = ModelConfiguration.objects.get_or_create(
        name=f"{purpose}:{model}",
        defaults={"provider": "openai", "model": model, "purpose": purpose},
    )
    template, _ = PromptTemplate.objects.get_or_create(
        name=purpose,
        version=1,
        defaults={"purpose": purpose, "system_prompt": "s", "user_template": "u"},
    )
    ai_run = AIRun.objects.create(
        edition=target,
        model_configuration=configuration,
        prompt_template=template,
        status=status,
        input_tokens=input_tokens,
        cached_input_tokens=0,
        output_tokens=output_tokens,
        estimated_cost_usd=Decimal(cost) if cost is not None else None,
    )
    if created_at is not None:
        AIRun.objects.filter(pk=ai_run.pk).update(created_at=created_at)
    return ai_run


def test_sums_every_run_per_purpose_and_model_inside_the_window() -> None:
    target = edition()
    now = timezone.now()
    run(
        target, purpose="translation", model="terra", input_tokens=100, output_tokens=50, cost="0.5"
    )
    run(target, purpose="translation", model="terra", input_tokens=10, output_tokens=5, cost="0.05")
    run(target, purpose="translation", model="luna", input_tokens=1, output_tokens=1, cost="0.001")
    run(
        target,
        purpose="alignment_adjudication",
        model="luna",
        input_tokens=7,
        output_tokens=3,
        cost=None,
        status=AIRun.Status.FAILED,
    )
    run(
        target,
        purpose="import_metadata",
        model="luna",
        input_tokens=999,
        output_tokens=999,
        cost="9",
        created_at=now - timedelta(days=40),
    )

    report = ai_spend(now - timedelta(days=30), now + timedelta(seconds=1))

    assert report["lines"] == [
        {
            "purpose": "alignment_adjudication",
            "model": "luna",
            "runs": 1,
            "input_tokens": 7,
            "cached_input_tokens": 0,
            "output_tokens": 3,
            "reasoning_tokens": 0,
            "estimated_cost_usd": "0.000000",
        },
        {
            "purpose": "translation",
            "model": "luna",
            "runs": 1,
            "input_tokens": 1,
            "cached_input_tokens": 0,
            "output_tokens": 1,
            "reasoning_tokens": 0,
            "estimated_cost_usd": "0.001000",
        },
        {
            "purpose": "translation",
            "model": "terra",
            "runs": 2,
            "input_tokens": 110,
            "cached_input_tokens": 0,
            "output_tokens": 55,
            "reasoning_tokens": 0,
            "estimated_cost_usd": "0.550000",
        },
    ]


def test_internal_endpoint_needs_the_shared_token_and_an_aware_window(monkeypatch) -> None:
    monkeypatch.setenv("ALMONIUM_BOOKS_PUBLISHER_TOKEN", SECRET)
    target = edition()
    run(
        target, purpose="translation", model="terra", input_tokens=100, output_tokens=50, cost="0.5"
    )
    client = APIClient()
    since = (timezone.now() - timedelta(days=7)).isoformat()

    assert client.get("/api/v1/internal/ai-spend/", {"since": since}).status_code == 403

    naive = client.get(
        "/api/v1/internal/ai-spend/",
        {"since": "2026-09-01T00:00:00"},
        HTTP_X_ALMONIUM_BOOKS_TOKEN=SECRET,
    )
    assert naive.status_code == 400

    response = client.get(
        "/api/v1/internal/ai-spend/",
        {"since": since},
        HTTP_X_ALMONIUM_BOOKS_TOKEN=SECRET,
    )
    assert response.status_code == 200
    assert response.json()["since"] == since
    assert [line["estimated_cost_usd"] for line in response.json()["lines"]] == ["0.500000"]
