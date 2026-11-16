def test_a_job_records_a_refusal_and_its_own_messages_in_full_and_anything_else_by_type():
    from almonium_book_processor.ai.cli_calls import AllowanceUsedUp, NetworkDown, recorded_error

    assert recorded_error(AllowanceUsedUp("You've hit your limit")).startswith("Allowance used up")
    assert recorded_error(NetworkDown("EAI_AGAIN")).startswith("Network unreachable")
    assert recorded_error(ValueError("Protected block changed: c1.vs21"), ValueError) == (
        "Protected block changed: c1.vs21"
    )
    # an error that may quote the book is named by its type only
    assert recorded_error(ValueError("Call me Ishmael.")) == "ValueError"
    assert recorded_error(KeyError("text")) == "KeyError"
