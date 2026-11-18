import json

import pytest

from almonium_book_processor.ai.cli_calls import AllowanceUsedUp
from almonium_book_processor.catalog import sentence_adjudication as adjudication
from almonium_book_processor.catalog.models import (
    AIRun,
    AlignmentJudgment,
    EditionArtifact,
    PipelineRun,
)
from almonium_book_processor.catalog.offline_sentence_alignment import processor_version
from almonium_book_processor.catalog.parallel_content import inherited_payload, pair_hash
from tests.catalog.test_sentence_alignment import pair  # noqa: F401

pytestmark = pytest.mark.django_db

MODEL = "gpt-5.6-luna"
OFFLINE = processor_version()


class Fake:
    """A provider that answers every stretch with ``groups`` and counts its calls."""

    def __init__(self, groups=None, error=None):
        self.groups = groups or [{"primary": [0], "secondary": [0], "certain": True}]
        self.error = error
        self.bodies = []

    def __call__(self, seat):
        return self

    def respond(self, body):
        self.bodies.append(body)
        if self.error:
            raise self.error
        items = json.loads(body["input"])["items"]
        answer = {"items": [{"id": item["id"], "groups": self.groups} for item in items]}
        return {
            "id": "response-1",
            "output": [
                {
                    "type": "message",
                    "content": [{"type": "output_text", "text": json.dumps(answer)}],
                }
            ],
            "usage": {"input_tokens": 1000, "output_tokens": 100},
        }


@pytest.fixture
def aligned(pair, settings):  # noqa: F811
    """The pair's one paragraph, its first sentence confirmed offline and its second not."""

    settings.AI_PLANS = ""
    primary, secondary = pair
    run = PipelineRun.objects.create(
        edition=primary,
        stage=PipelineRun.Stage.ALIGN,
        status=PipelineRun.Status.SUCCEEDED,
        processor_version=OFFLINE,
        summary={"secondary_id": str(secondary.id)},
    )
    p, s = primary.blocks.get(), secondary.blocks.get()
    EditionArtifact.objects.create(
        edition=primary,
        kind=EditionArtifact.Kind.SENTENCE_ALIGNMENT,
        input_hash=pair_hash(p, s),
        processor_version=OFFLINE,
        pipeline_run=run,
        payload={
            "method": "offline_embeddings",
            "groups": [
                {"primary": [0], "secondary": [0], "certain": True, "similarity": 0.95},
                {
                    "primary": [1],
                    "secondary": [1],
                    "certain": False,
                    "similarity": 0.7,
                    "acceptance": "uncertain",
                },
            ],
        },
    )
    return run


def judge(run, fake, **options):
    return adjudication.adjudicate(
        adjudication.paragraphs(run),
        model_setting=MODEL,
        edition_id=run.edition_id,
        provider=fake,
        **options,
    )


def test_only_the_unconfirmed_stretch_is_shown_and_its_answer_is_bought_once(aligned):
    fake = Fake()
    tally = judge(aligned, fake)
    assert (tally.regions, tally.answered, tally.calls, tally.written) == (1, 1, 1, 1)
    item = json.loads(fake.bodies[0]["input"])["items"][0]
    # the confirmed first sentence is never sent
    assert item["primary"] == [{"n": 0, "text": "Again."}]
    assert item["secondary"] == [{"n": 0, "text": "Again."}]
    artifact = EditionArtifact.objects.get(processor_version=f"{adjudication.VERSION}:{MODEL}")
    assert artifact.payload["groups"] == [
        {"primary": [0], "secondary": [0], "certain": True, "similarity": 0.95},
        {"primary": [1], "secondary": [1], "certain": True, "acceptance": "llm_adjudication"},
    ]
    run = AIRun.objects.get()
    assert run.status == AIRun.Status.SUCCEEDED and run.estimated_cost_usd > 0
    assert "Again" not in json.dumps(run.request_payload)

    again = judge(aligned, fake)
    assert (again.found, again.calls, again.written) == (1, 0, 0)
    assert len(fake.bodies) == 1 and AIRun.objects.count() == 1


def test_the_reader_serves_the_judged_groups_over_the_offline_ones_they_were_made_from(aligned):
    primary, secondary = aligned.edition, aligned.edition.derived_editions.get()
    assert not inherited_payload(primary, secondary)["blocks"][0]["sentence_alignment"][1][
        "certain"
    ]
    judge(aligned, Fake())
    block = inherited_payload(primary, secondary)["blocks"][0]
    assert block["sentence_alignment"][1]["certain"]
    assert block["alignment_provenance"]["adjudicated_by"] == MODEL
    # read from the other side, the same verdict
    assert inherited_payload(secondary, primary)["blocks"][0]["sentence_alignment"][1]["certain"]


def test_a_judgment_is_found_by_its_clauses_under_a_later_offline_version(aligned, monkeypatch):
    judge(aligned, Fake())
    later = "offline-sentence-v11:abc"
    EditionArtifact.objects.filter(processor_version=OFFLINE).update(processor_version=later)
    PipelineRun.objects.filter(pk=aligned.pk).update(processor_version=later)
    aligned.refresh_from_db()
    primary, secondary = aligned.edition, aligned.edition.derived_editions.get()
    # the artifact made from the earlier offline version no longer stands in for anything
    monkeypatch.setattr(
        "almonium_book_processor.catalog.offline_sentence_alignment.processor_version",
        lambda model=None: later,
    )
    block = inherited_payload(primary, secondary)["blocks"][0]
    assert not block["sentence_alignment"][1]["certain"]

    fake = Fake()
    tally = judge(aligned, fake)
    assert (tally.found, tally.calls, tally.written) == (1, 0, 1)
    assert not fake.bodies
    assert inherited_payload(primary, secondary)["blocks"][0]["sentence_alignment"][1]["certain"]


def test_an_answer_that_does_not_cover_the_stretch_is_asked_twice_and_then_left(aligned):
    fake = Fake(groups=[{"primary": [0, 1], "secondary": [0], "certain": True}])
    first = judge(aligned, fake)
    assert (first.unusable, first.written) == (1, 0)
    second = judge(aligned, fake)
    assert second.unusable == 1
    third = judge(aligned, fake)
    assert (third.given_up, third.calls) == (1, 0)
    assert len(fake.bodies) == 2
    assert AlignmentJudgment.objects.get().attempts == 2
    assert not EditionArtifact.objects.filter(
        processor_version__startswith=adjudication.VERSION
    ).exists()


def test_a_refused_allowance_holds_the_pass_and_counts_no_attempt(aligned):
    held = judge(aligned, Fake(error=AllowanceUsedUp("You've hit your usage limit")))
    assert "Allowance used up" in held.held
    assert not AlignmentJudgment.objects.exists()
    assert "Allowance used up" in AIRun.objects.get().error

    tally = judge(aligned, Fake())
    assert (tally.answered, tally.written) == (1, 1)
    assert AIRun.objects.get().status == AIRun.Status.SUCCEEDED
    assert AlignmentJudgment.objects.get().attempts == 1


def test_a_paid_call_killed_before_its_answers_were_kept_is_read_not_asked_again(aligned):
    judge(aligned, Fake())
    AlignmentJudgment.objects.all().delete()
    EditionArtifact.objects.filter(processor_version__startswith=adjudication.VERSION).delete()
    fake = Fake()
    tally = judge(aligned, fake)
    assert (tally.reread, tally.calls, tally.answered, tally.written) == (1, 0, 1, 1)
    assert not fake.bodies


def test_consecutive_unconfirmed_groups_are_one_stretch_and_may_be_paired_out_of_order(aligned):
    artifact = EditionArtifact.objects.get(processor_version=OFFLINE)
    artifact.payload["groups"][0]["certain"] = False
    artifact.save()
    crossed = [
        {"primary": [0], "secondary": [1], "certain": True},
        {"primary": [1], "secondary": [0], "certain": False},
    ]
    fake = Fake(groups=crossed)
    tally = judge(aligned, fake)
    item = json.loads(fake.bodies[0]["input"])["items"][0]
    assert [clause["text"] for clause in item["primary"]] == ["Hello.", "Again."]
    assert (tally.before_groups, tally.after_groups, tally.after_certain, tally.reordered) == (
        2,
        2,
        1,
        1,
    )
    written = EditionArtifact.objects.get(processor_version__startswith=adjudication.VERSION)
    assert [(g["primary"], g["secondary"], g["certain"]) for g in written.payload["groups"]] == [
        ([0], [1], True),
        ([1], [0], False),
    ]


def test_a_stretch_too_long_to_ask_is_counted_and_left(aligned, monkeypatch):
    monkeypatch.setattr(adjudication, "REGION_LIMIT", 0)
    fake = Fake()
    tally = judge(aligned, fake)
    assert (tally.oversized, tally.regions, tally.calls) == (1, 0, 0)


def test_a_paragraph_with_a_punctuation_only_sentence_waits_for_its_resplit(aligned):
    block = aligned.edition.blocks.get()
    block.text = "Hello. « Again."
    block.sentences = [{"start": 0, "end": 6}, {"start": 7, "end": 8}, {"start": 9, "end": 15}]
    block.save()
    assert adjudication._lone_marks(block)
    EditionArtifact.objects.update(
        input_hash=pair_hash(block, aligned.edition.derived_editions.get().blocks.get())
    )
    assert adjudication.paragraphs(aligned) == []
