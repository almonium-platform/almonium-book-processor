"""Deterministic projections of validated windows; never calls an AI provider."""

from __future__ import annotations

import math
import re
from collections import Counter

from django.db import transaction
from django.utils import timezone

from almonium_book_processor.catalog.models import (
    AIRun,
    Chapter,
    Edition,
    EditionArtifact,
    PipelineRun,
)

DIFFICULTY_VERSION = "chapter-difficulty-v1"
SUMMARY_VERSION = "chapter-summary-v1"
BOOK_VERSION = "book-difficulty-v1"
KINDS = (EditionArtifact.Kind.DIFFICULTY, EditionArtifact.Kind.CHAPTER_SUMMARY)
LEVELS = ("A1", "A2", "B1", "B2", "C1", "C2")


def percentile(levels: list[str], weights: list[int] | None = None) -> str | None:
    if not levels:
        return None
    counts = Counter()
    for level, weight in zip(levels, weights or [1] * len(levels), strict=True):
        counts[level] += weight
    threshold = math.ceil(sum(counts.values()) * 0.75)
    cumulative = 0
    for level in LEVELS:
        cumulative += counts[level]
        if cumulative >= threshold:
            return level
    return None


def role_signature(edition: Edition) -> list:
    return list(edition.chapters.order_by("sequence").values_list("id", "analysis_role"))


def _roles(edition: Edition) -> list:
    return [[str(pk), role] for pk, role in role_signature(edition)]


def _tokens(data: dict) -> int:
    # Deliberately named whitespace tokens, not model tokens or lexical/NLP facts.
    return sum(len(re.findall(r"\S+", block["text"])) for block in data["blocks"])


def build_payloads(plan: dict, roles: dict, results: dict) -> tuple[list, dict]:
    """Complete chapters alone enter the book percentile; partial chapter estimates are labelled."""
    chapters = []
    for chapter in plan["chapters"]:
        windows = [w for w in plan["windows"] if w["data"]["chapter_id"] == chapter["id"]]
        available = [(w, results[w["hash"]]) for w in windows if w["hash"] in results]
        common = {
            "chapter_id": chapter["id"],
            "chapter_hash": chapter["hash"],
            "windows_total": len(windows),
            "windows_completed": len(available),
            "complete": len(available) == len(windows),
            "whitespace_tokens_total": sum(_tokens(w["data"]) for w in windows),
            "whitespace_tokens_analyzed": sum(_tokens(w["data"]) for w, _ in available),
        }
        levels = [r.response_payload["analysis"]["cefr_estimate"] for _, r in available]
        weights = [_tokens(w["data"]) for w, _ in available]
        confidences = [r.response_payload["analysis"]["confidence"] for _, r in available]
        details = []
        summaries = []
        for window, result in available:
            analysis = result.response_payload["analysis"]
            provenance = {
                "window": window["data"]["window"],
                "window_hash": window["hash"],
                "ai_run_id": str(result.id),
            }
            details.append(
                {
                    **provenance,
                    **{
                        key: analysis[key]
                        for key in (
                            "cefr_estimate",
                            "confidence",
                            "archaism_score",
                            "modernisation_would_help",
                            "evidence",
                            "hard_words",
                            "content_flags",
                        )
                    },
                    "evidence_spans": result.response_payload["evidence_spans"],
                }
            )
            summaries.append(
                {
                    **provenance,
                    **{
                        key: analysis[key]
                        for key in (
                            "spoiler_free_description",
                            "recap",
                            "themes",
                            "characters",
                            "setting",
                        )
                    },
                }
            )
        difficulty = {
            **common,
            "cefr_estimate": percentile(levels, weights),
            "min_level": min(levels, key=LEVELS.index) if levels else None,
            "max_level": max(levels, key=LEVELS.index) if levels else None,
            "confidence_min": min(confidences) if confidences else None,
            "confidence_max": max(confidences) if confidences else None,
            "archaism_score": round(
                sum(
                    w * r.response_payload["analysis"]["archaism_score"]
                    for w, (_, r) in zip(weights, available, strict=True)
                )
                / sum(weights),
                4,
            )
            if weights
            else None,
            "method": "whitespace-token-weighted-window-p75",
            "windows": details,
        }
        summary = {**common, "method": "ordered-window-sections", "sections": summaries}
        chapters.append(
            {
                "id": chapter["id"],
                "role": roles[chapter["id"]],
                "difficulty": difficulty,
                "summary": summary,
            }
        )
    eligible = [c["difficulty"] for c in chapters if c["role"] == Chapter.AnalysisRole.BODY]
    complete = [c for c in eligible if c["complete"]]
    levels = [c["cefr_estimate"] for c in complete]
    weights = [c["whitespace_tokens_total"] for c in complete]
    confidence_min = [c["confidence_min"] for c in complete]
    confidence_max = [c["confidence_max"] for c in complete]
    book = {
        "analysis_input_hash": plan["hash"],
        "roles": roles,
        "method": "nearest-rank-chapter-p75",
        "cefr_estimate": percentile(levels),
        "weighted_comparison": percentile(levels, weights),
        "weighting": "non-whitespace-token-count-v1",
        "min_level": min(levels, key=LEVELS.index) if levels else None,
        "max_level": max(levels, key=LEVELS.index) if levels else None,
        "distribution": {level: levels.count(level) for level in LEVELS},
        "chapters_total": len(eligible),
        "chapters_completed": len(complete),
        "chapters_excluded": len(chapters) - len(eligible),
        "complete": bool(eligible) and len(complete) == len(eligible),
        "whitespace_tokens_total": sum(c["whitespace_tokens_total"] for c in eligible),
        "whitespace_tokens_analyzed": sum(c["whitespace_tokens_analyzed"] for c in eligible),
        "confidence_min": min(confidence_min) if confidence_min else None,
        "confidence_max": max(confidence_max) if confidence_max else None,
    }
    return chapters, book


def refresh_projections(run_id: str, *, token: str | None = None) -> None:
    from almonium_book_processor.catalog.chapter_analysis import (
        StaleAnalysis,
        _hash,
        analysis_spec,
        snapshot,
    )

    # Lock source blocks as well as the edition: normal text revisions lock the
    # block first, then update the edition. Follow the same order to avoid deadlocks.
    run = PipelineRun.objects.filter(id=run_id, stage=PipelineRun.Stage.CHAPTER_ANALYSIS).first()
    if run is None:
        return
    with transaction.atomic():
        edition_id = run.edition_id
        from almonium_book_processor.catalog.models import ContentBlock

        list(ContentBlock.objects.select_for_update().filter(edition_id=edition_id).order_by("id"))
        edition = (
            Edition.objects.select_for_update().select_related("work").filter(id=edition_id).first()
        )
        if edition is None:
            return
        list(edition.chapters.select_for_update().order_by("id"))
        run.refresh_from_db()
        if token is not None and run.summary.get("lease") != token:
            raise StaleAnalysis("Another worker took over chapter analysis.")
        spec = run.summary["spec"]
        plan = snapshot(edition, spec)
        if plan["hash"] != run.input_hash:
            raise StaleAnalysis("Text changed before chapter results could be projected.")
        hashes = [w["hash"] for w in plan["windows"]]
        results = {}
        for result in AIRun.objects.filter(
            edition=edition,
            status=AIRun.Status.SUCCEEDED,
            input_hash__in=hashes,
        ).order_by("created_at", "id"):
            # Keep the first validated result, matching reuse rather than mixing attempts.
            results.setdefault(result.input_hash, result)
        roles = dict(_roles(edition))
        chapters, book = build_payloads(plan, roles, results)
        retained = []

        def persist(kind, payload, chapter_id=None):
            payload = {**payload, "analysis_spec_hash": _hash(spec)}
            version = (
                BOOK_VERSION
                if chapter_id is None
                else (DIFFICULTY_VERSION if kind == KINDS[0] else SUMMARY_VERSION)
            )
            digest = _hash([kind, chapter_id, version, payload])
            artifact, _ = EditionArtifact.objects.get_or_create(
                edition=edition,
                kind=kind,
                input_hash=digest,
                processor_version=version,
                defaults={
                    "chapter_id": chapter_id,
                    "pipeline_run": run,
                    "payload": payload,
                    "is_current": False,
                },
            )
            retained.append(artifact.id)
            return artifact

        for chapter in chapters:
            for kind, key in ((KINDS[0], "difficulty"), (KINDS[1], "summary")):
                artifact = persist(kind, chapter[key], chapter["id"])
                chapter[f"{key}_artifact_id"] = str(artifact.id)
        book["chapter_artifacts"] = [
            {key: c[key] for key in ("id", "role", "difficulty_artifact_id")} for c in chapters
        ]
        persist(KINDS[0], book)
        # A late old-model completion may add history, but must not displace
        # projections from the currently configured analysis model.
        if spec == analysis_spec(edition.language):
            edition.artifacts.filter(kind__in=KINDS, is_current=True).exclude(
                id__in=retained
            ).update(is_current=False)
            edition.artifacts.filter(id__in=retained).update(is_current=True)
            from almonium_book_processor.catalog.adaptation_quality import sync_difficulty_warning

            sync_difficulty_warning(edition, run)
            apply_analysis_level(edition, book)


def apply_analysis_level(edition: Edition, book: dict | None) -> bool:
    """Label the edition with a complete book estimate; return whether it changed.

    Chapter analysis is the authority on an original's level: it runs on the
    whole text under a pinned rubric, and nobody re-reads a book to second-guess
    it. An editor may still pick a level, and that choice stands until they
    clear it. An adaptation is labelled with the level it was generated for
    when its review passes, not with the estimate, which the gate keeps at or
    below that target. A parallel translation borrows the level with its source.
    """

    from almonium_book_processor.catalog.adaptation_quality import adaptation_target

    if not book or not book.get("complete") or book.get("cefr_estimate") not in LEVELS:
        return False
    if edition.cefr_level_source == Edition.LevelSource.EDITOR or adaptation_target(edition):
        return False
    level = book["cefr_estimate"]
    changed = (edition.cefr_level, edition.cefr_level_source) != (
        level,
        Edition.LevelSource.ANALYSIS,
    )
    edition.cefr_level = level
    edition.cefr_level_source = Edition.LevelSource.ANALYSIS
    edition.save(update_fields=["cefr_level", "cefr_level_source", "updated_at"])
    Edition.objects.filter(
        source_edition=edition,
        parallel_role=Edition.ParallelRole.PARALLEL,
        edition_type=Edition.EditionType.MACHINE_TRANSLATION,
    ).exclude(cefr_level_source=Edition.LevelSource.EDITOR).update(
        cefr_level=level, cefr_level_source=Edition.LevelSource.ANALYSIS, updated_at=timezone.now()
    )
    return changed


def projection_context(edition: Edition, analysis: dict) -> dict:
    from almonium_book_processor.catalog.chapter_analysis import _hash, analysis_spec

    state = "pending"
    run = analysis.get("chapter_analysis_run")
    data = None
    rows = []
    if run:
        if analysis.get("chapter_analysis_stale"):
            state = "stale"
        else:
            # Text reverts can reactivate an older matching projection on worker refresh.
            candidates = edition.artifacts.filter(
                kind=KINDS[0],
                chapter__isnull=True,
                is_current=True,
                processor_version=BOOK_VERSION,
            )
            artifact = next(
                (
                    a
                    for a in candidates
                    if a.payload.get("analysis_input_hash") == run.input_hash
                    and a.payload.get("analysis_spec_hash")
                    == _hash(analysis_spec(edition.language))
                    and a.payload.get("roles") == dict(_roles(edition))
                ),
                None,
            )
            if artifact:
                data = artifact.payload
                state = "complete" if data["complete"] else "partial"
                if not data["chapters_total"]:
                    state = "empty"
                elif not data["whitespace_tokens_analyzed"]:
                    state = "pending"
                ids = [entry["difficulty_artifact_id"] for entry in data["chapter_artifacts"]]
                artifacts = {
                    str(a.id): a
                    for a in edition.artifacts.filter(
                        id__in=ids,
                        is_current=True,
                        processor_version=DIFFICULTY_VERSION,
                    )
                }
                if len(artifacts) != len(ids):
                    return {
                        "projection_state": "stale",
                        "book_difficulty": None,
                        "chapter_projections": [],
                    }
                summaries = {
                    str(a.chapter_id): a
                    for a in edition.artifacts.filter(
                        kind=KINDS[1],
                        chapter__isnull=False,
                        is_current=True,
                        processor_version=SUMMARY_VERSION,
                    )
                }
                for chapter in edition.chapters.order_by("sequence"):
                    entry = next(
                        (c for c in data["chapter_artifacts"] if c["id"] == str(chapter.id)), None
                    )
                    if entry:
                        difficulty = artifacts[entry["difficulty_artifact_id"]].payload
                        summary = summaries.get(str(chapter.id))
                        summary_payload = (
                            summary.payload
                            if summary
                            and (
                                summary.payload["chapter_hash"] == difficulty["chapter_hash"]
                                and summary.payload["analysis_spec_hash"]
                                == difficulty["analysis_spec_hash"]
                            )
                            else None
                        )
                        rows.append(
                            {
                                "chapter": chapter,
                                "difficulty": difficulty,
                                "summary": summary_payload,
                            }
                        )
            elif edition.artifacts.filter(kind__in=KINDS).exists():
                state = "stale"
        if (
            run.status in (PipelineRun.Status.FAILED, PipelineRun.Status.CANCELLED)
            and state != "stale"
        ):
            state = "failed"
        elif (
            run.status in (PipelineRun.Status.QUEUED, PipelineRun.Status.RUNNING)
            and state == "pending"
        ):
            state = run.status
    return {"projection_state": state, "book_difficulty": data, "chapter_projections": rows}


def enqueue_projection(run_id: str) -> None:
    from almonium_book_processor.catalog.tasks import project_chapter_analysis

    def dispatch():
        try:
            project_chapter_analysis.delay(run_id)
        except Exception:
            raise ValueError("Could not queue the projection refresh. Please retry.") from None

    transaction.on_commit(dispatch)


def queue_projection_refresh(edition_id: str) -> None:
    from almonium_book_processor.catalog.chapter_analysis import analysis_spec, snapshot

    edition = Edition.objects.select_related("work").get(id=edition_id)
    plan = snapshot(edition, analysis_spec(edition.language))
    run = edition.pipeline_runs.filter(
        stage=PipelineRun.Stage.CHAPTER_ANALYSIS,
        input_hash=plan["hash"],
    ).first()
    if run is None:
        raise ValueError("Analyze the current text before refreshing its projections.")
    enqueue_projection(str(run.id))


@transaction.atomic
def set_chapter_role(edition_id: str, chapter_id: str, role: str) -> None:
    from almonium_book_processor.catalog.models import Work

    if role not in Chapter.AnalysisRole.values:
        raise ValueError("Choose a valid chapter role.")
    edition = Edition.objects.select_for_update().select_related("work").get(id=edition_id)
    if edition.work.visibility != Work.Visibility.PUBLIC:
        raise ValueError("Chapter analysis is available only for public editions.")
    chapter = edition.chapters.select_for_update().filter(id=chapter_id).first()
    if chapter is None:
        raise ValueError("Chapter does not belong to this edition.")
    chapter.analysis_role = role
    chapter.save(update_fields=["analysis_role", "updated_at"])
    edition.artifacts.filter(kind=KINDS[0], chapter__isnull=True, is_current=True).update(
        is_current=False
    )
