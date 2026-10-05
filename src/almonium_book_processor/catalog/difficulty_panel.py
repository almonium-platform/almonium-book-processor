"""What the edition page's reading-difficulty panel shows, derived from the assessment.

For an adaptation with a target, each chapter's level is the one the gate reads
(the level judges' reading of its wording where they have one, otherwise the
chapter analysis's highest window), so the verdict, the chapter chips and the
gate callout all count the same thing. Windows and their evidence always come
from the chapter analysis, and the panel says so.
"""

from almonium_book_processor.catalog.chapter_projections import LEVELS, percentile

LEVEL_INDEX = {level: index for index, level in enumerate(LEVELS)}
SHOWN_EVIDENCE = 2


def _gate_level(row: dict) -> str | None:
    return row.get("wording_level") or row["difficulty"].get("max_level")


def cited_block_ids(assessment: dict) -> set[str]:
    """Every block the analysis cites as evidence, so the page can link each to the reader."""

    return {
        item["block_id"]
        for row in assessment.get("chapter_projections", [])
        for window in row["difficulty"].get("windows", [])
        for item in window.get("evidence", [])
    }


def _evidence(items: list[dict], blocks: dict) -> list[dict]:
    return [
        {
            **item,
            "dimension": item.get("dimension", "").capitalize(),
            "uuid": blocks.get(item["block_id"]),
        }
        for item in items
    ]


def difficulty_panel(assessment: dict, blocks: dict | None = None) -> dict:
    blocks = blocks or {}
    book = assessment.get("book_difficulty") or {}
    target = assessment.get("adaptation_target")
    rows = []
    for row in assessment.get("chapter_projections", []):
        difficulty = row["difficulty"]
        level = _gate_level(row) if target else difficulty.get("cefr_estimate")
        level = level if level in LEVEL_INDEX else None
        sections = {s["window"]: s for s in row.get("summary", {}).get("sections", [])}
        windows = []
        for window in difficulty.get("windows", []):
            evidence = _evidence(window.get("evidence", []), blocks)
            section = sections.get(window["window"], {})
            windows.append(
                {
                    "number": window["window"],
                    "level": window["cefr_estimate"],
                    "archaism": window.get("archaism_score"),
                    "evidence": evidence[:SHOWN_EVIDENCE],
                    "more_evidence": evidence[SHOWN_EVIDENCE:],
                    "evidence_count": len(evidence),
                    "description": section.get("spoiler_free_description"),
                    "recap": section.get("recap"),
                }
            )
        above = bool(row.get("above_adaptation_target"))
        body = row["chapter"].analysis_role == "body"
        analysis_level = difficulty.get("cefr_estimate")
        rows.append(
            {
                "chapter": row["chapter"],
                "level": level,
                "within_target": bool(
                    target and level and LEVEL_INDEX[level] <= LEVEL_INDEX[target]
                ),
                # Above the target counts against the gate only in a body chapter.
                "above": above and body,
                "above_ungated": above and not body,
                "judges": row.get("wording_judges") or [],
                "analysis_level": analysis_level if target and analysis_level != level else None,
                "complete": difficulty.get("complete"),
                "windows": windows,
            }
        )

    body = [r for r in rows if r["chapter"].analysis_role == "body" and r["complete"]]
    if target and body:
        levels = [r["level"] for r in body if r["level"]]
        counts = {level: levels.count(level) for level in LEVELS}
        estimate = percentile(levels)
    else:
        counts = book.get("distribution") or {}
        estimate = book.get("cefr_estimate")
    analysis_estimate = book.get("cefr_estimate")

    roles = {}
    for r in rows:
        roles[r["chapter"].analysis_role] = roles.get(r["chapter"].analysis_role, 0) + 1
    above_rows = [r for r in rows if r["above"]]
    blocker = assessment.get("adaptation_blocker") or ""
    below = assessment.get("adaptation_below_chapters") or []
    return {
        "target": target,
        "blocker": blocker,
        "passing": bool(target) and not blocker,
        "estimate": estimate,
        "analysis_estimate": (
            analysis_estimate if target and analysis_estimate != estimate else None
        ),
        "distribution": [(level, counts.get(level, 0)) for level in LEVELS if counts.get(level)],
        "body_count": roles.get("body", 0),
        "front_count": roles.get("front", 0),
        "back_count": roles.get("back", 0),
        "above_chapters": above_rows,
        "above_count": len(above_rows),
        "flagged_count": sum(1 for r in rows if r["above"] or r["above_ungated"]),
        "below_chapters": below,
        "rows": rows,
    }
