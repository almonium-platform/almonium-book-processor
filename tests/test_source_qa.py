from almonium_book_processor.processing.source_qa import SourceQABlock, analyze_source_quality


def frequencies(text: str, language: str) -> float:
    return {
        "abroad": 4.4,
        "ab road": 4.0,
        "something": 5.8,
        "some thing": 5.5,
        "misfortune": 4.0,
        "mis fortune": 3.5,
        "ab": 4.0,
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
