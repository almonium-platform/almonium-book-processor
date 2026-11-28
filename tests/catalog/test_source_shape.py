from almonium_book_processor.catalog.source_shape import judge, paragraph_shape, unreadable


def metrics(**overrides):
    base = {
        "chapters": 20,
        "body_chapters": 18,
        "chars": 300_000,
        "body_chars": 290_000,
        "largest_body_share": 0.09,
        "median_body_chars": 15_000,
        "tiny_body_chapters": 0,
        "first_sequence": 1,
        "first_role": "body",
        "matter_titles_in_body": [],
        "titles": [],
        "warnings": [],
        "language": "en",
    }
    return {**base, **overrides}


def test_a_book_cut_at_its_chapters_is_sound():
    assert judge(metrics()) == ("ok", [])


def test_a_long_book_in_two_pieces_was_not_cut_at_its_chapters():
    # A Christmas Carol on 15 October 2026: 157,000 characters in two chapters, one of them 91%
    verdict, reasons = judge(
        metrics(chapters=2, body_chapters=2, chars=157_000, largest_body_share=0.91)
    )
    assert verdict == "suspect"
    assert reasons == ["157,000 characters in 2 body chapter(s)"]


def test_a_short_story_in_one_piece_is_sound():
    assert judge(metrics(chapters=1, body_chapters=1, chars=30_000, largest_body_share=1.0)) == (
        "ok",
        [],
    )


def test_a_book_in_three_parts_is_sound_however_long():
    # Die Verwandlung and Heart of Darkness are three parts each
    assert judge(metrics(chapters=3, body_chapters=3, chars=121_000, largest_body_share=0.4)) == (
        "ok",
        [],
    )


def test_one_chapter_holding_half_the_book_among_many_is_a_missed_heading():
    verdict, reasons = judge(metrics(body_chapters=11, largest_body_share=0.49))
    assert verdict == "suspect" and reasons == ["one body chapter is 49% of the body"]


def test_the_gutenberg_preamble_and_the_contents_page_are_not_the_story():
    verdict, reasons = judge(
        metrics(
            matter_titles_in_body=["There are several editions of this ebook", "CONTENTS"],
            tiny_body_chapters=1,
        )
    )
    assert verdict == "suspect"
    # one short chapter among eighteen is a book's own short section, not a finding
    assert reasons == [
        "matter pages counted as body: There are several editions of this ebook, CONTENTS",
    ]


def test_many_tiny_chapters_are_a_cut_gone_wrong():
    # the Cambridge Shakespeare: 29 of 51 body chapters are a heading and a line
    verdict, reasons = judge(metrics(body_chapters=51, tiny_body_chapters=29))
    assert verdict == "suspect"
    assert reasons == ["29 of 51 body chapters under 400 characters"]


def test_a_book_with_no_body_chapter_is_suspect():
    assert judge(metrics(body_chapters=0, largest_body_share=None))[0] == "suspect"


def test_a_shape_report_is_signed_to_almonium_and_never_fails_without_it(monkeypatch):
    from almonium_book_processor.catalog import source_shape

    monkeypatch.delenv("ALMONIUM_API_URL", raising=False)
    assert (
        source_shape.report_shape("https://www.gutenberg.org/ebooks/84.epub3.images", "ok") is False
    )

    monkeypatch.setenv("ALMONIUM_API_URL", "https://api.example")
    monkeypatch.setenv("ALMONIUM_BOOKS_PUBLISHER_SECRET", "secret")
    posted = []
    monkeypatch.setattr(
        "almonium_book_processor.catalog.publication._signed_post",
        lambda path, payload, failure: posted.append((path, payload)),
    )
    assert (
        source_shape.report_shape("https://www.gutenberg.org/ebooks/84.epub3.images", "suspect")
        is True
    )
    assert posted == [
        (
            "/internal/books/sources/shape",
            {
                "downloadUrl": "https://www.gutenberg.org/ebooks/84.epub3.images",
                "verdict": "suspect",
            },
        )
    ]


LINE = "pałuby, która nie wie, czemu nią jest, czemu musi trwać w tej gwałtem"


def test_a_book_whose_paragraphs_are_lines_of_print_cannot_be_read():
    # Sklepy cynamonowe from Gutenberg 8119: 2,460 paragraphs, 69 characters, 5% end a sentence
    shape = paragraph_shape([LINE] * 950 + ["narzuconej formie, będącej parodią?"] * 50)
    assert shape == {"paragraphs": 1000, "long_paragraph_chars": 69, "sentence_end_share": 0.05}

    reason = unreadable(metrics(**shape))

    assert reason == (
        "The file has no paragraphs: each of its 1,000 is a line of the print, hardly one over "
        "69 characters and 5% of them ending a sentence."
    )
    assert judge(metrics(**shape)) == ("suspect", ["1,000 paragraphs that are lines of print"])


def test_dialogue_in_short_paragraphs_is_a_book():
    # every line is short, and every line ends where its sentence does
    shape = paragraph_shape(
        ["— Nie wiem — powiedziała Adela.", "— A ja wiem!", "«Bien sûr.»"] * 200
    )
    assert shape["long_paragraph_chars"] < 100 and shape["sentence_end_share"] == 1.0
    assert unreadable(metrics(**shape)) is None


def test_verse_set_a_line_to_a_paragraph_is_not_refused():
    # half its lines end on a full stop or a question; wrapped prose manages one in twenty
    shape = paragraph_shape(
        [
            "Litwo! Ojczyzno moja! ty jesteś jak zdrowie.",
            "Ile cię trzeba cenić, ten tylko się dowie,",
        ]
        * 300
    )
    assert unreadable(metrics(**shape)) is None


def test_real_paragraphs_and_a_short_text_are_left_alone():
    long = paragraph_shape([LINE * 6] * 300 + [LINE] * 300)
    assert long["long_paragraph_chars"] > 100 and unreadable(metrics(**long)) is None
    # too few paragraphs to tell a wrapped page from a list or a letter
    assert unreadable(metrics(**paragraph_shape([LINE] * 150))) is None
    # an ingest measured before paragraphs were counted has nothing to say
    assert unreadable(metrics()) is None
