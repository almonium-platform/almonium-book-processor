"""Live adaptation gates: editorial labels cannot override current text assessments."""

from almonium_book_processor.catalog.chapter_projections import LEVELS
from almonium_book_processor.catalog.models import Edition, PipelineRun


def adaptation_quality(edition, analysis=None):
    if edition.edition_type != Edition.EditionType.ADAPTATION:
        return {}
    targets = {
        value
        for value in edition.pipeline_runs.filter(
            stage=PipelineRun.Stage.ADAPT, processor_version="b2-book-v1"
        ).values_list("summary__target_level", flat=True)
        if value
    }
    targets.update(
        value
        for value in edition.blocks.values_list("attributes__adaptation__target_level", flat=True)
        if value
    )
    if not targets:
        # Independently imported adaptations do not yet have a generation target.
        return {"adaptation_target": None}
    if len(targets) != 1 or not targets.issubset(LEVELS):
        return {"adaptation_blocker": "Adaptation target metadata is inconsistent; review it."}
    target = next(iter(targets))
    if analysis is None:
        from almonium_book_processor.catalog.chapter_analysis import analysis_context

        analysis = analysis_context(edition)
    result = {"adaptation_target": target, "adaptation_blocker": ""}
    if analysis.get("projection_state") != "complete":
        result["adaptation_blocker"] = (
            f"Target {target}: complete, current difficulty estimates are required before "
            "review completion or publication."
        )
        return result
    above = []
    below = []
    if not analysis.get("chapter_projections"):
        result["adaptation_blocker"] = "Every adaptation chapter needs a current estimate."
        return result
    for row in analysis.get("chapter_projections", []):
        level = row["difficulty"].get("max_level")
        if level not in LEVELS or not row["difficulty"].get("complete"):
            result["adaptation_blocker"] = "Every adaptation chapter needs a current estimate."
            return result
        row["above_adaptation_target"] = LEVELS.index(level) > LEVELS.index(target)
        if row["above_adaptation_target"]:
            above.append(row["chapter"].sequence)
        if LEVELS.index(row["difficulty"]["cefr_estimate"]) < LEVELS.index(target):
            below.append(row["chapter"].sequence)
    result["adaptation_above_chapters"] = above
    result["adaptation_below_chapters"] = below
    if above:
        result["adaptation_blocker"] = (
            f"Target {target} not achieved: {len(above)} chapter(s) contain above-target "
            f"estimates ({', '.join(map(str, above))}). Review the cited passages and revise "
            "the text or assessment. Changing the editorial label does not clear this gate."
        )
    return result


def adaptation_blocker(edition):
    return adaptation_quality(edition).get("adaptation_blocker", "")
