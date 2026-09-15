import json
import uuid
from types import SimpleNamespace

import pytest

from almonium_book_processor.catalog.models import AIRun, Chapter, ContentBlock, Edition, Work
from almonium_book_processor.catalog.parallel_content import inherited_payload
from almonium_book_processor.catalog.sentence_alignment import (
    generate_sentence_preview,
    validate_mapping,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def pair():
    work = Work.objects.create(slug="sentences", title="Book")
    original = Edition.objects.create(
        work=work, slug="original", language="en", parallel_role="canonical", status="published"
    )
    target = Edition.objects.create(
        work=work,
        slug="adapted",
        language="en",
        source_edition=original,
        parallel_role="parallel",
        status="published",
    )
    group = uuid.uuid4()
    for edition in (original, target):
        chapter = Chapter.objects.create(edition=edition, sequence=11, title="V")
        ContentBlock.objects.create(
            edition=edition,
            chapter=chapter,
            block_id="c11.p1",
            sequence=1,
            align_group=group,
            text="Hello. Again." if edition == original else "Hello! Again.",
            sentences=[{"start": 0, "end": 6}, {"start": 7, "end": 13}],
        )
    return original, target


def test_inherited_public_pair_and_private_boundary(client, pair):
    response = client.get("/api/v1/public/editions/original/parallel/adapted/")
    assert response.status_code == 200
    assert response.json()["blocks"][0]["primary_block_id"] == "c11.p1"
    pair[1].status = "review"
    pair[1].save()
    assert client.get("/api/v1/public/editions/original/parallel/adapted/").status_code == 404
    pair[0].work.visibility = "private"
    pair[0].work.save()
    assert client.get("/api/v1/public/editions/original/parallel/adapted/").status_code == 404


def test_missing_or_duplicate_groups_refuse_inherited_pair(pair):
    p, s = pair
    block = s.blocks.get()
    block.align_group = uuid.uuid4()
    block.save()
    assert inherited_payload(p, s) is None


def test_identical_sentences_need_no_paid_alignment(pair, monkeypatch):
    p, s = pair
    s.blocks.update(text=p.blocks.get().text)
    monkeypatch.setattr(
        "almonium_book_processor.catalog.sentence_alignment.OpenAIBatchProvider",
        lambda: pytest.fail("Identical text must not call AI"),
    )
    generate_sentence_preview(str(p.id), str(s.id), 11)
    assert not AIRun.objects.exists()
    assert p.artifacts.get(kind="sentence_alignment").payload["method"] == "identical_text"


def test_preview_requires_staff(client, pair):
    from django.contrib.auth import get_user_model

    p, s = pair
    url = f"/editions/{p.id}/sentence-preview/{s.id}/?chapter=11"
    assert client.get(url).status_code == 302
    staff = get_user_model().objects.create_user(username="preview", is_staff=True)
    client.force_login(staff)
    response = client.get(url)
    assert response.status_code == 200
    assert b"sentence-data" in response.content


def test_failed_output_is_recorded_and_retryable(monkeypatch, pair):
    class Fake:
        def respond(self, body):
            return {"id": "failed-output", "output": []}

    monkeypatch.setattr(
        "almonium_book_processor.catalog.sentence_alignment.OpenAIBatchProvider", Fake
    )
    p, s = pair
    for _ in range(2):
        with pytest.raises(ValueError):
            generate_sentence_preview(str(p.id), str(s.id), 11)
    assert AIRun.objects.count() == 1
    assert AIRun.objects.get().status == "failed"


def test_sentence_groups_are_many_to_many_not_zipped():
    p = SimpleNamespace(sentences=[{}, {}, {}])
    s = SimpleNamespace(sentences=[{}])
    mapping = {"groups": [{"primary": [0, 1, 2], "secondary": [0], "certain": True}]}
    assert validate_mapping(mapping, p, s) == mapping
    mapping["groups"][0]["primary"] = [0, 1, 1]
    with pytest.raises(ValueError):
        validate_mapping(mapping, p, s)


def test_paid_preview_cached_and_invalidated(monkeypatch, pair):
    calls = []
    mapping = {"groups": [{"primary": [0, 1], "secondary": [0, 1], "certain": True}]}

    class Fake:
        def respond(self, body):
            calls.append(body)
            assert json.loads(body["input"])["primary"] == ["Hello.", "Again."]
            return {
                "id": "fake",
                "output": [
                    {
                        "type": "message",
                        "content": [{"type": "output_text", "text": json.dumps(mapping)}],
                    }
                ],
            }

    monkeypatch.setattr(
        "almonium_book_processor.catalog.sentence_alignment.OpenAIBatchProvider", Fake
    )
    p, s = pair
    generate_sentence_preview(str(p.id), str(s.id), 11)
    generate_sentence_preview(str(p.id), str(s.id), 11)
    assert len(calls) == 1
    assert AIRun.objects.get().status == "succeeded"
    assert inherited_payload(p, s)["blocks"][0]["sentence_alignment"] == mapping["groups"]
    assert inherited_payload(s, p)["blocks"][0]["sentence_alignment"] == mapping["groups"]
    s.blocks.update(text="Changed.")
    assert inherited_payload(p, s)["blocks"][0]["sentence_alignment"] == []
