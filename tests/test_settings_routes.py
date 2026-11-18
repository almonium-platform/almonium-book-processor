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
        # the marginal notes can be written on a plan too
        "almonium_book_processor.catalog.tasks.generate_chapter_glosses",
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


def test_a_bare_model_on_a_plan_sends_the_generating_tasks_to_the_host_worker():
    assert plan_task_routes("gpt-5.6-terra", plans="codex")
    assert plan_task_routes("gpt-5.6-terra", plans="") == {}


def test_each_step_with_a_model_alone_goes_to_the_host_worker_when_its_model_is_on_a_plan():
    from almonium_book_processor.config.settings import step_task_routes

    models = {
        "quality": "gpt-5.6-terra",
        "draft": "gpt-5.6-luna",
        "primary": "openai:gpt-5.6-luna",
        "escalation": "openai:gpt-5.6-terra",
        "metadata": "gpt-5.6-luna",
    }
    assert step_task_routes(models, plans="") == {}
    routed = {name.rsplit(".", 1)[1] for name in step_task_routes(models, plans="codex")}
    assert routed == {
        "translate_edition_inline",
        "prepare_translation",
        "translate_edition_metadata",
        "modernisation_advice",
        "detect_edition_metadata",
    }


def test_the_step_routed_names_are_real_tasks():
    from almonium_book_processor.catalog import tasks
    from almonium_book_processor.config.settings import STEP_TASKS

    for names, _ in STEP_TASKS:
        for name in names:
            assert getattr(tasks, name).name == f"almonium_book_processor.catalog.tasks.{name}"
