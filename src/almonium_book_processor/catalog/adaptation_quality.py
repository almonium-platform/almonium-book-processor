"""Live adaptation gates: editorial labels cannot override current text assessments."""

from almonium_book_processor.catalog.chapter_projections import LEVELS
from almonium_book_processor.catalog.models import Edition, PipelineRun

DIFFICULTY_WARNING = "adaptation_difficulty_gate"


def adaptation_target(edition) -> str | None:
    """The single CEFR level an adaptation was generated for, if it has one."""
    if edition.edition_type != Edition.EditionType.ADAPTATION:
        return None
    targets = _targets(edition)
    if len(targets) == 1 and targets.issubset(LEVELS):
        return next(iter(targets))
    return None


def _targets(edition) -> set:
    targets = {
        value
        for value in edition.pipeline_runs.filter(
            stage=PipelineRun.Stage.ADAPT, processor_version__in=("b1-book-v1", "b2-book-v1")
        ).values_list("summary__target_level", flat=True)
        if value
    }
    targets.update(
        value
        for value in edition.blocks.values_list("attributes__adaptation__target_level", flat=True)
        if value
    )
    return targets


def adaptation_quality(edition, analysis=None):
    if edition.edition_type != Edition.EditionType.ADAPTATION:
        return {}
    targets = _targets(edition)
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


def sync_difficulty_warning(edition, run):
    """Called with the edition locked after current worker projections are saved."""
    from django.utils import timezone

    from almonium_book_processor.catalog.models import QAWarning

    quality = adaptation_quality(edition)
    blocker = quality.get("adaptation_blocker")
    if blocker:
        QAWarning.objects.update_or_create(
            edition=edition,
            code=DIFFICULTY_WARNING,
            defaults={
                "severity": QAWarning.Severity.WARNING,
                "message": blocker,
                "source_ref": f"chapter-analysis:{run.id}",
                "resolved_at": None,
                "resolved_by": None,
            },
        )
    elif quality.get("adaptation_target"):
        edition.warnings.filter(code=DIFFICULTY_WARNING, resolved_at=None).update(
            resolved_at=timezone.now(),
            resolved_by=None,
        )
