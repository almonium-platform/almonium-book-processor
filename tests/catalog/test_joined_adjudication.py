"""A model reads the stretches a join through the original left unconfirmed, and only those."""

import json
from io import StringIO

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.urls import reverse

from almonium_book_processor.ai.cli_calls import AllowanceUsedUp
from almonium_book_processor.catalog import sentence_adjudication as adjudication
from almonium_book_processor.catalog import sentence_bridge
from almonium_book_processor.catalog.models import AIRun, AlignmentJudgment, EditionArtifact
from almonium_book_processor.catalog.parallel_content import inherited_payload, pair_hash
from tests.catalog.test_sentence_adjudication import Fake
from tests.catalog.test_sentence_bridge import align, tree  # noqa: F401

pytestmark = pytest.mark.django_db

MODEL = "gpt-5.6-luna"
JUDGED = f"{adjudication.VERSION}:{MODEL}"


@pytest.fixture
def doubted(tree, settings):  # noqa: F811
    """The adaptation and the French are each aligned with the original; the French
    alignment left the second sentence of the first paragraph unconfirmed."""

    settings.AI_PLANS = ""
    settings.SENTENCE_ADJUDICATION_MODEL = MODEL
    original, adapted, french, _ukrainian = tree
    runs = align(original, adapted), align(original, french)
    artifact = EditionArtifact.objects.get(
        input_hash=pair_hash(
            original.blocks.get(block_id="c1.p1"), french.blocks.get(block_id="c1.p1")
        )
    )
    artifact.payload["groups"][1]["certain"] = False
    artifact.save(update_fields=["payload"])
    return original, adapted, french, runs


def second_group(edition, other):
    return inherited_payload(edition, other)["blocks"][0]["sentence_alignment"][1]


def test_only_the_unconfirmed_stretch_of_a_join_is_read_and_it_is_bought_once(doubted):
    _original, adapted, french, _runs = doubted
    # Whoever asks, the pair is read in one order: the adaptation first.
    (paragraph,) = adjudication.joined_paragraphs(french, adapted)
    block = adapted.blocks.get(block_id="c1.p1")
    assert paragraph.primary == block
    assert paragraph.artifact.edition_id == adapted.id
    assert paragraph.artifact.input_hash == pair_hash(block, french.blocks.get(block_id="c1.p1"))
    (region,) = paragraph.regions
    assert region.texts == {"primary": ["Again."], "secondary": ["Encore."]}
    assert region.languages == ("en", "fr")

    fake = Fake()
    tally = adjudication.adjudicate_joined(french, adapted, provider=fake, workers=1)

    assert (tally.regions, tally.answered, tally.calls, tally.written) == (1, 1, 1, 1)
    item = json.loads(fake.bodies[0]["input"])["items"][0]
    # the confirmed first sentence is never sent
    assert item["primary"] == [{"n": 0, "text": "Again."}]
    assert item["secondary"] == [{"n": 0, "text": "Encore."}]
    artifact = EditionArtifact.objects.get(processor_version=JUDGED)
    assert artifact.edition == adapted and artifact.pipeline_run is None
    assert artifact.payload["adjudication"]["base"] == sentence_bridge.VERSION
    first, second = artifact.payload["groups"]
    assert (first["certain"], first["acceptance"]) == (True, "bridged")
    assert second == {
        "primary": [1],
        "secondary": [1],
        "certain": True,
        "acceptance": "llm_adjudication",
        "granularity": "clause",
    }
    call = AIRun.objects.get()
    assert call.edition == adapted and call.estimated_cost_usd > 0
    assert "Again" not in json.dumps(call.request_payload)

    for asked_from in ((adapted, french), (french, adapted)):
        again = adjudication.adjudicate_joined(*asked_from, provider=fake, workers=1)
        assert (again.found, again.calls, again.written) == (1, 0, 0)
    assert len(fake.bodies) == 1 and AIRun.objects.count() == 1
    assert EditionArtifact.objects.filter(processor_version=JUDGED).count() == 1


def test_the_reader_serves_the_judged_join_from_either_side(doubted):
    _original, adapted, french, _runs = doubted
    assert not second_group(adapted, french)["certain"]

    adjudication.adjudicate_joined(adapted, french, provider=Fake(), workers=1)

    first, second = inherited_payload(adapted, french)["blocks"]
    assert first["sentence_alignment"][1]["certain"]
    provenance = first["alignment_provenance"]
    assert provenance["adjudicated_by"] == MODEL
    assert (provenance["made_from"], provenance["stretches_left"]) == (sentence_bridge.VERSION, 0)
    assert second_group(french, adapted)["certain"]
    # A paragraph with nothing to ask is still the join, computed as it is read.
    assert second["alignment_provenance"]["processor_version"] == sentence_bridge.VERSION


def test_a_verdict_of_not_the_same_stays_a_question_and_is_not_asked_again(doubted):
    _original, adapted, french, _runs = doubted
    unsure = Fake(groups=[{"primary": [0], "secondary": [0], "certain": False}])

    adjudication.adjudicate_joined(adapted, french, provider=unsure, workers=1)

    group = second_group(adapted, french)
    assert (group["certain"], group["acceptance"]) == (False, "llm_adjudication")
    assert adjudication.joined_unread(adapted, french, inherited_payload(adapted, french)) is None
    again = adjudication.adjudicate_joined(adapted, french, provider=unsure, workers=1)
    assert (again.found, again.calls) == (1, 0)


def test_a_pair_aligned_directly_is_not_read_as_a_join(doubted):
    _original, adapted, french, _runs = doubted
    adjudication.adjudicate_joined(adapted, french, provider=Fake(), workers=1)
    run = align(adapted, french)

    assert adjudication.joined_paragraphs(adapted, french) == []
    for row in inherited_payload(adapted, french)["blocks"]:
        assert row["alignment_provenance"]["pipeline_run_id"] == str(run.id)


def test_what_a_revision_retires_comes_back_from_the_judgments_already_paid(doubted):
    _original, adapted, french, _runs = doubted
    adjudication.adjudicate_joined(adapted, french, provider=Fake(), workers=1)
    # What a text revision does to every artifact kept under the edition it touched.
    adapted.artifacts.filter(is_current=True).update(is_current=False)
    assert not second_group(adapted, french)["certain"]

    assert adjudication.restore_joined(french) == 0
    assert adjudication.restore_joined(adapted) == 1

    assert second_group(adapted, french)["certain"]
    assert AIRun.objects.count() == 1 and AlignmentJudgment.objects.count() == 1
    assert adjudication.restore_joined(adapted) == 0


def test_the_restore_follows_the_adjudication_of_the_edition_s_own_alignment(doubted, monkeypatch):
    _original, adapted, french, (adapted_run, _french_run) = doubted
    adjudication.adjudicate_joined(adapted, french, provider=Fake(), workers=1)
    adapted.artifacts.filter(is_current=True).update(is_current=False)
    monkeypatch.setattr(adjudication, "TASK_WORKERS", 1)
    refusing = Fake(error=AssertionError("nothing may be asked"))
    monkeypatch.setattr(adjudication.gateway, "provider", refusing)

    adjudication.adjudicate_run(adapted_run.id)

    assert second_group(adapted, french)["certain"]
    assert not refusing.bodies and AIRun.objects.count() == 1


def test_the_task_reads_the_pair_and_waits_out_a_refused_plan(doubted, monkeypatch):
    from celery.exceptions import Retry

    from almonium_book_processor.catalog import tasks

    _original, adapted, french, _runs = doubted
    monkeypatch.setattr(adjudication, "TASK_WORKERS", 1)
    arguments = [str(french.id), str(adapted.id)]
    refused = Fake(error=AllowanceUsedUp("You've hit your usage limit"))
    monkeypatch.setattr(adjudication.gateway, "provider", refused)
    with pytest.raises(Retry):
        tasks.adjudicate_joined_alignment.apply(args=arguments, throw=True)
    assert not second_group(adapted, french)["certain"]

    monkeypatch.setattr(adjudication.gateway, "provider", Fake())
    assert tasks.adjudicate_joined_alignment.apply(args=arguments).get() == {
        "answered": 1,
        "written": 1,
    }
    assert second_group(adapted, french)["certain"]


def test_the_alignment_page_prices_the_reading_and_queues_it_where_a_plan_is(
    client, doubted, settings, monkeypatch
):
    from almonium_book_processor.catalog import tasks

    original, adapted, french, _runs = doubted
    queued = []
    monkeypatch.setattr(tasks.adjudicate_joined_alignment, "delay", lambda *ids: queued.append(ids))
    client.force_login(get_user_model().objects.create_user(username="staff", is_staff=True))
    url = reverse("catalog:sentence-preview", args=[adapted.id, french.id])

    # No plan serves the model here: the page says what is unread, and offers nothing.
    settings.SENTENCE_ADJUDICATION_MODEL = "claude-sonnet-5-5"
    page = client.get(url)
    assert page.context["unread"]["count"] == 1 and page.context["unread"]["blocked"]
    html = page.content.decode()
    assert "1 unconfirmed stretch no model has read" in html and 'type="submit"' not in html
    assert client.post(url).status_code == 302 and not queued

    settings.AI_PLANS = "claude-code"
    page = client.get(url)
    unread = page.context["unread"]
    assert (unread["count"], unread["blocked"]) == (1, "")
    assert 0 < unread["estimate"].usd < 1
    html = page.content.decode()
    assert "Read 1 unconfirmed stretch" in html and 'class="cost"' in html
    # The pair has no job of its own to offer.
    assert "Align all" not in html and "Align this pair directly" not in html
    assert client.post(url).status_code == 302
    assert queued == [(str(adapted.id), str(french.id))]

    # Once read, nothing is left to offer, whatever the verdict.
    settings.AI_PLANS = ""
    settings.SENTENCE_ADJUDICATION_MODEL = MODEL
    adjudication.adjudicate_joined(adapted, french, provider=Fake(), workers=1)
    settings.SENTENCE_ADJUDICATION_MODEL = "claude-sonnet-5-5"
    settings.AI_PLANS = "claude-code"
    page = client.get(url)
    assert page.context["unread"] is None
    assert 'type="submit"' not in page.content.decode()
    # An aligned pair's page keeps its own button.
    direct = client.get(reverse("catalog:sentence-preview", args=[original.id, french.id]))
    assert direct.context["unread"] is None
    assert "Align all 1 chapter" in direct.content.decode()


def test_the_command_reads_the_pairs_in_different_languages_and_prices_them_first(
    doubted, settings, monkeypatch
):
    _original, adapted, french, _runs = doubted
    settings.OPENAI_API_KEY = "test"
    fake = Fake()
    monkeypatch.setattr(adjudication.gateway, "provider", fake)

    out = StringIO()
    call_command("adjudicate_sentence_alignment", "--joined", "--dry-run", stdout=out)
    assert "1 edition pair(s), 1 paragraph(s), 1 distinct stretch(es)" in out.getvalue()
    assert "1 to ask in about 1 call(s)" in out.getvalue()
    assert not fake.bodies and not AIRun.objects.exists()

    out = StringIO()
    call_command("adjudicate_sentence_alignment", "--joined", "--workers", "1", stdout=out)
    assert "adapted + french: 1 stretch(es) in 1 paragraph(s)" in out.getvalue()
    assert "1 answered in 1 call(s)" in out.getvalue()
    assert second_group(adapted, french)["certain"]

    out = StringIO()
    call_command("adjudicate_sentence_alignment", "--joined", "--workers", "1", stdout=out)
    assert "1 already paid" in out.getvalue() and len(fake.bodies) == 1
