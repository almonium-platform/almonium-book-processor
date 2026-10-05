from __future__ import annotations

from almonium_book_processor.config.settings import PLAN_QUEUE, plan_task_routes


def test_nothing_is_routed_to_the_plan_queue_without_a_plan_seat():
    assert plan_task_routes("") == {}
    assert plan_task_routes("openai:gpt-5.6-terra") == {}


def test_a_plan_seat_sends_the_generating_tasks_to_the_host_worker():
    routes = plan_task_routes("codex:gpt-6-astra")

    assert set(routes) == {
        "almonium_book_processor.catalog.tasks.adapt_chapter_pilot",
        "almonium_book_processor.catalog.tasks.adapt_book",
        "almonium_book_processor.catalog.tasks.run_floor_probe",
        "almonium_book_processor.catalog.tasks.audit_edition_fidelity",
        # where judges are configured they are the chapter analysis
        "almonium_book_processor.catalog.tasks.analyze_edition_chapters",
        # a production mends chapters itself, through the adapter and the judges
        "almonium_book_processor.catalog.tasks.produce_edition",
        # and has a translation written and reviewed on the plans
        "almonium_book_processor.catalog.tasks.translate_edition_on_plan",
        "almonium_book_processor.catalog.tasks.review_edition_translation",
    }
    assert all(route == {"queue": PLAN_QUEUE} for route in routes.values())


def test_a_plan_judge_or_auditor_alone_also_sends_them_there():
    # the adaptation tasks judge and audit too, so the generator on the API is not enough
    assert plan_task_routes("", "claude-code:claude-opus-5-5,codex:gpt-6.1-sol", "")
    assert plan_task_routes("openai:gpt-5.6-terra", "", "openai:x, codex:gpt-6.1-sol:medium")
    assert plan_task_routes("", "openai:gpt-6.1-sol", "") == {}


def test_the_routed_names_are_real_tasks():
    from almonium_book_processor.catalog import tasks

    for name in plan_task_routes("claude-code:claude-opus-5-5"):
        assert getattr(tasks, name.rsplit(".", 1)[1]).name == name
