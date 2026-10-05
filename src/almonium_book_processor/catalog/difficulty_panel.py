"""What the edition page's reading-difficulty panel shows, derived from the assessment.

For an adaptation with a target, each chapter's level is the one the gate reads
(the level judges' reading of its wording where they have one, otherwise the
chapter analysis's highest window), so the verdict, the bar, the chapter chips
and the gate callout all count the same thing.
"""

from almonium_book_processor.catalog.chapter_projections import LEVELS, percentile

LEVEL_INDEX = {level: index for index, level in enumerate(LEVELS)}
# The role select is a narrow column; the model's labels are for forms with room.
ROLE_CHOICES = (("body", "Substantive"), ("front", "Front matter"), ("back", "Back matter"))


def _gate_level(row: dict) -> str | None:
    return row.get("wording_level") or row["difficulty"].get("max_level")


def difficulty_panel(assessment: dict) -> dict:
    book = assessment.get("book_difficulty") or {}
    target = assessment.get("adaptation_target")
    rows = []
    for row in assessment.get("chapter_projections", []):
        difficulty = row["difficulty"]
        level = _gate_level(row) if target else difficulty.get("cefr_estimate")
        sections = {s["window"]: s for s in row.get("summary", {}).get("sections", [])}
        windows = [
            {
                "number": window["window"],
                "level": window["cefr_estimate"],
                "archaism": window.get("archaism_score"),
                "evidence": window.get("evidence", []),
                "description": sections.get(window["window"], {}).get("spoiler_free_description"),
                "recap": sections.get(window["window"], {}).get("recap"),
            }
            for window in difficulty.get("windows", [])
        ]
        rows.append(
            {
                "chapter": row["chapter"],
                "level": level if level in LEVEL_INDEX else None,
                "within_target": bool(
                    target and level in LEVEL_INDEX and LEVEL_INDEX[level] <= LEVEL_INDEX[target]
                ),
                "above": bool(row.get("above_adaptation_target")),
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
    total = sum(counts.values())
    segments = [
        {
            "level": level,
            "count": counts.get(level, 0),
            # Any share at all reads as a fill; the rest scales with it.
            "fill": round(25 + 75 * counts[level] / total) if total and counts.get(level) else 0,
            "is_target": level == target,
        }
        for level in LEVELS
    ]

    above = assessment.get("adaptation_above_chapters") or []
    blocker = assessment.get("adaptation_blocker") or ""
    return {
        "target": target,
        "blocker": blocker,
        "passing": bool(target) and not blocker,
        "estimate": estimate,
        "analysis_estimate": book.get("cefr_estimate"),
        "segments": segments if total else [],
        "above_count": len(above),
        "above_title": (
            f"{len(above)} chapter{'' if len(above) == 1 else 's'} read above {target}"
            if above
            else ""
        ),
        "rows": rows,
        "role_choices": ROLE_CHOICES,
        "above_rows": sum(1 for r in rows if r["above"]),
    }
