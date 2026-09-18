from almonium_book_processor.processing.source_qa import SourceQABlock, analyze_source_quality


def frequencies(text: str, language: str) -> float:
    return {
        "abroad": 4.4,
        "ab road": 4.0,
        "something": 5.8,
        "some thing": 5.5,
        "misfortune": 4.0,
        "mis fortune": 3.5,
        "ab": 1.8,
        "road": 5.2,
        "some": 4.0,
        "thing": 5.7,
        "mis": 3.0,
        "fortune": 4.5,
    }.get(text, 0.0)


def test_source_qa_detects_overlapping_split_words_and_broken_hyphenation() -> None:
    findings = analyze_source_quality(
        [
            SourceQABlock(
                "block-1",
                "c1.p1",
                1,
                "He went ab road after some thing caused a mis-\nfortune.",
            )
        ],
        "en",
        frequency_lookup=frequencies,
    )

    assert [(item.code, item.original_text, item.suggested_text) for item in findings] == [
        ("broken_hyphenation", "mis-\nfortune", "misfortune"),
        ("probable_split_word", "ab road", "abroad"),
    ]
    for finding in findings:
        assert finding.fingerprint() == finding.fingerprint()
    split = findings[1]
    assert split.evidence["fragment"] == "ab"
    assert split.confidence == 0.76


def test_source_qa_leaves_real_short_words_alone() -> None:
    # Real wordfreq scores: "cri" and "ras" are ordinary French words that are
    # merely rarer than "crise" and "auras". Neither pair is a split word.
    frequency = {
        "crise": 4.88,
        "cri se": 4.1,
        "cri": 4.1,
        "se": 6.56,
        "auras": 4.46,
        "au ras": 4.02,
        "au": 6.78,
        "ras": 4.02,
    }
    findings = analyze_source_quality(
        [
            SourceQABlock("one", "c20.p70", 20, "quand un cri se fit entendre"),
            SourceQABlock("two", "c20.p71", 20, "apparut au ras de l'eau"),
        ],
        "fr",
        frequency_lookup=lambda text, language: frequency.get(text, 0.0),
    )

    assert findings == []


def test_source_qa_split_word_confidence_grows_with_fragment_rarity_and_attestation() -> None:
    frequency = {"crise": 4.88, "se": 6.56, "cr": 0.0, "ise": 0.0}
    blocks = [
        SourceQABlock("one", "c1.p1", 1, "une cr ise grave"),
        SourceQABlock("two", "c1.p2", 1, "La crise dura. Une crise encore."),
    ]

    [finding] = analyze_source_quality(
        blocks, "fr", frequency_lookup=lambda text, language: frequency.get(text, 0.0)
    )
    assert (finding.original_text, finding.suggested_text) == ("cr ise", "crise")
    assert finding.evidence["attested_joined_occurrences"] == 2
    assert finding.confidence == 0.98

    [finding] = analyze_source_quality(
        blocks[:1], "fr", frequency_lookup=lambda text, language: frequency.get(text, 0.0)
    )
    assert finding.confidence == 0.9


def test_source_qa_lets_the_edition_vouch_for_an_ambiguous_fragment() -> None:
    # Real scores: "vo" (3.74) is web debris the frequency list cannot tell
    # from a rare word. It counts as a fragment only when "voici" is spelled
    # out elsewhere in the book and "vo" never stands alone anywhere else.
    frequency = {"voici": 5.12, "vo": 3.74, "ici": 5.71, "au": 6.78, "ras": 4.02, "auras": 4.46}
    lookup = lambda text, language: frequency.get(text, 0.0)  # noqa: E731
    vouched = [
        SourceQABlock("one", "c1.p1", 1, "Et vo ici la maison."),
        SourceQABlock("two", "c1.p2", 1, "Voici la porte. Voici le jardin."),
    ]
    [finding] = analyze_source_quality(vouched, "fr", frequency_lookup=lookup)
    assert (finding.suggested_text, finding.confidence) == ("voici", 0.718)
    assert finding.evidence["fragment_occurrences"] == 1

    # The same pair with no joined spelling elsewhere stays quiet.
    assert analyze_source_quality(vouched[:1], "fr", frequency_lookup=lookup) == []
    # A fragment that recurs as its own word is a word, however the joined form fares.
    recurring = vouched + [SourceQABlock("three", "c1.p3", 1, "Le vo du plan.")]
    assert analyze_source_quality(recurring, "fr", frequency_lookup=lookup) == []
    # "au ras" never qualifies: "auras" is not spelled out anywhere in the book.
    ras = [SourceQABlock("four", "c20.p71", 20, "apparut au ras de l'eau")]
    assert analyze_source_quality(ras, "fr", frequency_lookup=lookup) == []


def test_source_qa_flags_boilerplate_unicode_and_duplicate_blocks() -> None:
    duplicated = "This sufficiently long paragraph is duplicated accidentally. " * 3
    findings = analyze_source_quality(
        [
            SourceQABlock("one", "c1.p1", 1, "Project Gutenberg text\ufffd"),
            SourceQABlock("two", "c1.p2", 1, duplicated),
            SourceQABlock("three", "c1.p3", 1, duplicated),
        ],
        "en",
        frequency_lookup=lambda text, language: 0.0,
    )

    assert {item.code for item in findings} == {
        "gutenberg_boilerplate",
        "malformed_unicode",
        "duplicate_block",
    }
    malformed = next(item for item in findings if item.code == "malformed_unicode")
    assert malformed.suggested_text == ""
    duplicate = next(item for item in findings if item.code == "duplicate_block")
    assert duplicate.evidence == {"earlier_block_id": "c1.p2"}


def test_source_qa_detects_detached_block_initials_with_precise_offsets() -> None:
    frequency = {
        "the": 7.73,
        "t he": 5.41,
        "alice": 4.26,
        "a lice": 3.21,
        "eeyore": 2.32,
        "e eyore": 0.0,
    }
    findings = analyze_source_quality(
        [
            SourceQABlock("one", "c1.p2", 1, "T he answer was clear."),
            SourceQABlock("two", "c2.p2", 2, "\u201cA lice replied."),
            SourceQABlock("three", "c3.p2", 3, "E eyore sighed."),
        ],
        "en",
        frequency_lookup=lambda text, language: frequency.get(text, 0.0),
    )

    assert [
        (
            item.code,
            item.start_offset,
            item.end_offset,
            item.original_text,
            item.suggested_text,
        )
        for item in findings
    ] == [
        ("detached_initial", 0, 4, "T he", "The"),
        ("detached_initial", 1, 7, "A lice", "Alice"),
        ("detached_initial", 0, 7, "E eyore", "Eeyore"),
    ]


def test_source_qa_does_not_join_legitimate_or_noninitial_single_letters() -> None:
    frequency = {
        "along": 5.38,
        "a long": 5.8,
        "iran": 4.62,
        "i ran": 4.87,
        "tcell": 2.5,
        "t cell": 4.0,
        "the": 7.73,
        "t he": 5.41,
    }
    findings = analyze_source_quality(
        [
            SourceQABlock("one", "c1.p1", 1, "A long road remained."),
            SourceQABlock("two", "c1.p2", 1, "I ran home."),
            SourceQABlock("three", "c1.p3", 1, "T cell response."),
            SourceQABlock("four", "c1.p4", 1, "Then T he spoke."),
        ],
        "en",
        frequency_lookup=lambda text, language: frequency.get(text, 0.0),
    )

    assert findings == []


def test_short_drop_caps_and_corpus_attested_name():
    blocks = [
        SourceQABlock(str(i), f"c{i}.p2", i, text)
        for i, text in enumerate(
            [
                "I t was dark.",
                "W e returned.",
                "O n my return.",
                "M y life.",
                "C lerval returned.",
                "Clerval spoke with Clerval.",
                "A long road.",
                "I ran away.",
            ]
        )
    ]
    frequency = {
        "it": 6.9,
        "we": 6.5,
        "on": 6.9,
        "my": 6.5,
        "a long": 6,
        "along": 5,
        "i ran": 5,
        "iran": 4,
    }
    findings = analyze_source_quality(
        blocks, "en", frequency_lookup=lambda t, language: frequency.get(t, 0)
    )
    assert [f.suggested_text for f in findings if f.code == "detached_initial"] == [
        "It",
        "We",
        "On",
        "My",
        "Clerval",
    ]
