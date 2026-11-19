"""Two editions made from the same original are read through it, not aligned with each other."""

import uuid
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from almonium_book_processor.catalog import sentence_bridge
from almonium_book_processor.catalog.models import (
    Chapter,
    ContentBlock,
    Edition,
    EditionArtifact,
    PipelineRun,
    Work,
)
from almonium_book_processor.catalog.offline_sentence_alignment import (
    queue_alignment,
    run_alignment,
)
from almonium_book_processor.catalog.parallel_content import (
    common_origin,
    inherited_payload,
    pair_hash,
)
from almonium_book_processor.catalog.parallel_status import companion_rows, pair_status
from almonium_book_processor.catalog.sentence_alignment_queue import pairs_for
from almonium_book_processor.catalog.sentence_rows import chapter_rows

EMBED = "almonium_book_processor.processing.sentence_correspondence.embed_texts"


def block(count):
    """A block of ``count`` ten-character sentences."""

    return SimpleNamespace(
        sentences=[{"start": 11 * index, "end": 11 * index + 10} for index in range(count)]
    )


def group(origin, made, certain=True, **more):
    return {"primary": origin, "secondary": made, "certain": certain, **more}


def joined(result):
    return [(g["primary"], g["secondary"], g["certain"]) for g in result["groups"]]


def test_groups_meet_on_the_clauses_of_the_original():
    # The adaptation cuts the original's first clause in two; the translation runs its
    # second and third together. Each group is as coarse as the coarser side there.
    first = {
        "groups": [group([0], [0, 1]), group([1], [2]), group([2], [3]), group([3], [4])],
    }
    second = {"groups": [group([0], [0]), group([1, 2], [1]), group([3], [2])]}

    result = sentence_bridge.bridge(first, second, block(4), block(5), block(3))

    assert joined(result) == [([0, 1], [0], True), ([2, 3], [1], True), ([4], [2], True)]
    assert {g["acceptance"] for g in result["groups"]} == {"bridged"}
    assert result["primary_spans"] == block(5).sentences
    assert result["secondary_spans"] == block(3).sentences


def test_a_group_is_confirmed_only_when_everything_it_was_joined_from_was():
    first = {"groups": [group([0], [0]), group([1], [1], certain=False), group([2], [2])]}
    second = {"groups": [group([0], [0]), group([1], [1]), group([2], [2], certain=False)]}

    result = sentence_bridge.bridge(first, second, block(3), block(3), block(3))

    assert joined(result) == [([0], [0], True), ([1], [1], False), ([2], [2], False)]


def test_one_alignment_by_sentence_and_one_by_clause_meet_where_they_share_text():
    # The first alignment cut the original's second sentence into two clauses; the second
    # alignment kept whole sentences. Both clauses belong with that sentence.
    origin = SimpleNamespace(sentences=[{"start": 0, "end": 10}, {"start": 11, "end": 30}])
    clauses = [{"start": 0, "end": 10}, {"start": 11, "end": 20}, {"start": 21, "end": 30}]
    first = {
        "groups": [
            group([0], [0], granularity="sentence"),
            group([1], [1], granularity="clause"),
            group([2], [2], granularity="clause"),
        ],
        "primary_spans": clauses,
        "secondary_spans": clauses,
        "segmentation": "punctuation-clauses-v1",
    }
    second = {"groups": [group([0], [0]), group([1], [1])]}

    result = sentence_bridge.bridge(first, second, origin, block(2), block(2))

    assert joined(result) == [([0], [0], True), ([1, 2], [1], True)]
    assert [g["granularity"] for g in result["groups"]] == ["sentence", "clause"]
    assert result["primary_spans"] == clauses
    assert result["segmentation"] == "punctuation-clauses-v1"


def test_what_one_side_left_out_has_no_counterpart_and_is_not_confirmed():
    # The adaptation has nothing for the original's second sentence; the translation does.
    first = {"groups": [group([0], [0]), group([1], [])]}
    second = {"groups": [group([0], [0]), group([1], [1])]}

    result = sentence_bridge.bridge(first, second, block(2), block(1), block(2))

    assert joined(result) == [([0], [0], True), ([], [1], False)]


def test_nothing_is_joined_where_either_alignment_is_missing():
    aligned = {"groups": [group([0], [0])]}
    assert sentence_bridge.bridge(aligned, {"groups": []}, block(1), block(1), block(1)) is None
    assert sentence_bridge.bridge({}, aligned, block(1), block(1), block(1)) is None


# --- The reader's payload and the staff pages ---------------------------------------------


OPENING = {"Hello.", "Hello!", "Hullo!", "Bonjour.", "Привіт.", "Night.", "Night!", "Nuit.", "Ніч."}


def fake_embed(texts, **_):
    """A block's first sentence one way and its second the other, in every language.

    By the text, not its place in the call: an original aligned with a second companion is
    not embedded again, so the call for that companion holds other texts in other places.
    """

    return [[1, 0] if text in OPENING else [0, 1] for text in texts]


def spans(text):
    """Two one-word sentences separated by a space."""

    first, _second = text.split(" ")
    return [{"start": 0, "end": len(first)}, {"start": len(first) + 1, "end": len(text)}]


@pytest.fixture
def tree(db):
    """An original with an adaptation and two translations, two blocks each."""

    work = Work.objects.create(slug="tree", title="Book")
    original = Edition.objects.create(
        work=work, slug="original", language="en", parallel_role="canonical", status="published"
    )
    made = {}
    for slug, language, kind, level in (
        ("adapted", "en", "adaptation", "B1"),
        ("french", "fr", "machine_translation", None),
        ("ukrainian", "uk", "machine_translation", None),
    ):
        made[slug] = Edition.objects.create(
            work=work,
            slug=slug,
            language=language,
            cefr_level=level,
            edition_type=kind,
            source_edition=original,
            parallel_role="parallel",
            status="published",
        )
    groups = [uuid.uuid4(), uuid.uuid4()]
    for edition, texts in (
        (original, ("Hello. Again.", "Night. Falls.")),
        (made["adapted"], ("Hello! Again.", "Night! Falls.")),
        (made["french"], ("Bonjour. Encore.", "Nuit. Tombe.")),
        (made["ukrainian"], ("Привіт. Знову.", "Ніч. Падає.")),
    ):
        chapter = Chapter.objects.create(edition=edition, sequence=1, title="I")
        for index, text in enumerate(texts):
            ContentBlock.objects.create(
                edition=edition,
                chapter=chapter,
                block_id=f"c1.p{index + 1}",
                sequence=index + 1,
                align_group=groups[index],
                text=text,
                sentences=spans(text),
            )
    return original, made["adapted"], made["french"], made["ukrainian"]


def align(primary, secondary):
    with patch(EMBED, side_effect=fake_embed):
        run = queue_alignment(primary.id, secondary.id, model="sentence-transformers/LaBSE")
        run_alignment(run.id)
    run.refresh_from_db()
    assert run.status == PipelineRun.Status.SUCCEEDED
    return run


def test_an_adaptation_and_a_translation_are_read_through_the_original(tree):
    original, adapted, french, _ukrainian = tree
    assert common_origin(adapted, french) == original
    assert common_origin(original, french) is None
    align(original, adapted)
    # Only one of the two is aligned with the original: nothing to join yet.
    assert not any(b["sentence_alignment"] for b in inherited_payload(adapted, french)["blocks"])

    align(original, french)
    runs = PipelineRun.objects.count()
    artifacts = EditionArtifact.objects.count()

    payload = inherited_payload(adapted, french)
    for row in payload["blocks"]:
        assert [(g["primary"], g["secondary"]) for g in row["sentence_alignment"]] == [
            ([0], [0]),
            ([1], [1]),
        ]
        assert all(g["certain"] for g in row["sentence_alignment"])
        assert {g["acceptance"] for g in row["sentence_alignment"]} == {"bridged"}
        provenance = row["alignment_provenance"]
        assert provenance["processor_version"] == sentence_bridge.VERSION
        assert provenance["bridged_through"] == "original"
        assert provenance["artifact_id"] is None
        assert len({leg["artifact_id"] for leg in provenance["legs"]}) == 2
        assert provenance["input_hash"] == row["revision"]
    # The other way round reads the same join, and nothing was run or stored for it.
    mirrored = inherited_payload(french, adapted)["blocks"][0]
    assert mirrored["primary_text"] == "Bonjour. Encore."
    assert [(g["primary"], g["secondary"]) for g in mirrored["sentence_alignment"]] == [
        ([0], [0]),
        ([1], [1]),
    ]
    assert PipelineRun.objects.count() == runs
    assert EditionArtifact.objects.count() == artifacts


def test_two_translations_are_read_through_the_original_whichever_way_each_was_aligned(tree):
    original, _adapted, french, ukrainian = tree
    align(original, french)
    align(ukrainian, original)

    row = inherited_payload(french, ukrainian)["blocks"][1]

    assert (row["primary_text"], row["secondary_text"]) == ("Nuit. Tombe.", "Ніч. Падає.")
    assert [(g["primary"], g["secondary"]) for g in row["sentence_alignment"]] == [
        ([0], [0]),
        ([1], [1]),
    ]


def test_a_long_book_is_read_in_several_queries_and_comes_out_the_same(tree, monkeypatch):
    original, adapted, french, _ukrainian = tree
    align(original, adapted)
    align(original, french)
    joined, direct = inherited_payload(adapted, french), inherited_payload(original, french)
    assert all(row["sentence_alignment"] for row in joined["blocks"] + direct["blocks"])

    monkeypatch.setattr("almonium_book_processor.catalog.parallel_content._DIGESTS_PER_QUERY", 1)

    assert inherited_payload(adapted, french) == joined
    assert inherited_payload(original, french) == direct


def test_an_unconfirmed_match_with_the_original_leaves_the_joined_group_unconfirmed(tree):
    original, adapted, french, _ukrainian = tree
    align(original, adapted)
    align(original, french)
    first = original.blocks.get(block_id="c1.p1")
    artifact = EditionArtifact.objects.get(
        input_hash=pair_hash(first, french.blocks.get(block_id="c1.p1"))
    )
    artifact.payload["groups"][1]["certain"] = False
    artifact.save(update_fields=["payload"])

    groups = inherited_payload(adapted, french)["blocks"][0]["sentence_alignment"]

    assert [g["certain"] for g in groups] == [True, False]
    rows, stats = chapter_rows(inherited_payload(adapted, french)["blocks"], adapted, french)
    assert [g["low"] for g in rows[0]["groups"]] == [False, True]
    assert (stats["groups"], stats["low"], stats["bridged"]) == (4, 1, 4)


def test_a_pair_aligned_directly_keeps_its_own_alignment(tree):
    original, adapted, french, _ukrainian = tree
    align(original, adapted)
    align(original, french)
    run = align(adapted, french)

    for row in inherited_payload(adapted, french)["blocks"]:
        assert row["alignment_provenance"]["pipeline_run_id"] == str(run.id)
        assert "legs" not in row["alignment_provenance"]


def test_a_changed_paragraph_falls_back_until_it_is_aligned_with_the_original_again(tree):
    original, adapted, french, _ukrainian = tree
    align(original, adapted)
    align(original, french)
    changed = adapted.blocks.get(block_id="c1.p1")
    ContentBlock.objects.filter(pk=changed.pk).update(
        text="Hullo! Again.", sentences=spans("Hullo! Again.")
    )

    first, second = inherited_payload(adapted, french)["blocks"]
    assert first["sentence_alignment"] == []
    assert first["alignment_provenance"] is None
    assert len(second["sentence_alignment"]) == 2

    align(original, adapted)
    assert len(inherited_payload(adapted, french)["blocks"][0]["sentence_alignment"]) == 2


def test_the_pair_itself_is_never_queued(tree):
    original, adapted, french, ukrainian = tree
    assert pairs_for(adapted) == [(original, adapted)]
    assert pairs_for(original) == [(original, adapted), (original, french), (original, ukrainian)]


def test_the_companion_table_says_what_the_join_is_waiting_for(tree):
    original, adapted, french, ukrainian = tree
    rows = {row["other"].slug: row for row in companion_rows(adapted)}
    assert rows["original"]["state"] == "missing"
    assert rows["french"]["state"] == "bridge-waiting"
    assert rows["french"]["waiting_for"] == [adapted, french]

    align(original, adapted)
    align(original, french)
    rows = {row["other"].slug: row for row in companion_rows(adapted)}
    assert (rows["original"]["state"], rows["french"]["state"]) == ("current", "bridged")
    assert rows["french"]["origin"] == original
    assert (rows["french"]["badge"], rows["french"]["waiting_for"]) == ("succeeded", [])
    assert rows["ukrainian"]["state"] == "bridge-waiting"
    assert rows["ukrainian"]["waiting_for"] == [ukrainian]
    # The pair's own state is untouched: nothing was run for it, and nothing will be.
    assert pair_status(adapted, french)["state"] == "missing"

    align(adapted, ukrainian)
    rows = {row["other"].slug: row for row in companion_rows(adapted)}
    assert rows["ukrainian"]["state"] == "current"
    assert "origin" not in rows["ukrainian"]


def test_the_staff_pages_show_the_join(client, tree):
    original, adapted, french, ukrainian = tree
    align(original, adapted)
    align(original, french)
    client.force_login(get_user_model().objects.create_user(username="staff", is_staff=True))

    page = client.get(reverse("catalog:edition-detail", args=[adapted.id]))
    assert page.status_code == 200
    assert page.context["parallel_companions_due"] == 0
    assert page.context["parallel_companions_waiting"] == 1
    html = page.content.decode()
    assert "1 pair waiting for the original" in html
    assert "Through the original" in html
    assert "and UK is not aligned with it yet" in html
    # No job is offered for a pair that is read through the original.
    assert reverse("catalog:queue-sentence-alignment", args=[adapted.id, french.id]) not in html
    assert reverse("catalog:queue-sentence-alignment", args=[adapted.id, ukrainian.id]) not in html

    preview = client.get(reverse("catalog:sentence-preview", args=[adapted.id, french.id]))
    assert preview.status_code == 200
    assert preview.context["origin"] == original
    html = preview.content.decode()
    assert "4 joined through the original" in html
    assert 'title="Joined through the original"' in html
    assert "Their groups are joined through it" in html
    # Running this pair's own job is still offered, and named for what it does.
    assert "Align this pair directly" in html
    direct = client.get(reverse("catalog:sentence-preview", args=[original.id, french.id]))
    assert direct.context["origin"] is None
    assert "joined through" not in direct.content.decode()
    assert "Align all 1 chapter" in direct.content.decode()
