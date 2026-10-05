"""The reader's Difficulty notes layer: the chapter analysis's evidence beside the text it cites.

Each evidence item becomes a card in the margin of the block it quotes, and its quote is
underlined in the text where the current wording still holds it. Editing a block makes
the analysis stale, but its last reading of the chapter still explains the text that is
left: every card on a block edited since then stays and says the text changed, until the
chapter is analysed again. Windows are cut the way the analysis cut
them, so each window's level, archaism and recap head the blocks it read.

Evidence carries no direction yet (whether a passage raises or eases the level), so every
item but a content flag is one neutral kind. Content flags describe what happens, not how
hard it reads, and keep a kind of their own.
"""

from almonium_book_processor.catalog.chapter_analysis import (
    _locate,
    analysis_context,
    analysis_spec,
    chapter_blocks,
    window_parts,
)
from almonium_book_processor.catalog.chapter_projections import DIFFICULTY_VERSION, SUMMARY_VERSION
from almonium_book_processor.catalog.models import ContentBlockRevision, EditionArtifact

LAYER = "difficulty"


def _reading(edition, chapter, analysis: dict) -> tuple[dict | None, object, bool]:
    """The analysis's latest reading of a chapter, when it was made, and whether it is current.

    A current projection is the reading itself. Once the text changes every projection is
    stale, and the chapter's last difficulty artifact is the reading the notes describe.
    """

    artifacts = EditionArtifact.objects.filter(
        edition=edition,
        chapter=chapter,
        kind=EditionArtifact.Kind.DIFFICULTY,
        processor_version=DIFFICULTY_VERSION,
    ).order_by("-created_at")
    projection = next(
        (r for r in analysis.get("chapter_projections", []) if r["chapter"].id == chapter.id),
        None,
    )
    if projection is not None:
        artifact = artifacts.filter(
            payload__chapter_hash=projection["difficulty"]["chapter_hash"]
        ).first()
        return projection, artifact.created_at if artifact else None, True
    artifact = artifacts.first()
    if artifact is None:
        return None, None, False
    summary = (
        EditionArtifact.objects.filter(
            edition=edition,
            chapter=chapter,
            kind=EditionArtifact.Kind.CHAPTER_SUMMARY,
            processor_version=SUMMARY_VERSION,
            payload__chapter_hash=artifact.payload["chapter_hash"],
        )
        .order_by("-created_at")
        .first()
    )
    row = {
        "chapter": chapter,
        "difficulty": artifact.payload,
        "summary": summary.payload if summary else None,
    }
    return row, artifact.created_at, False


def notes_available(edition, analysis: dict) -> bool:
    return (
        bool(analysis)
        and edition.artifacts.filter(
            kind=EditionArtifact.Kind.DIFFICULTY,
            chapter__isnull=False,
            processor_version=DIFFICULTY_VERSION,
        ).exists()
    )


def chapter_evidence_count(edition, chapter, analysis: dict) -> int:
    row, _, _ = _reading(edition, chapter, analysis)
    if row is None:
        return 0
    return sum(len(w.get("evidence", [])) for w in row["difficulty"].get("windows", []))


def _changed_blocks(blocks: list, since) -> set[str]:
    """Blocks whose text is not the text the analysis read: revised since, and not back."""

    if since is None:
        return set()
    read = {}
    for revision in ContentBlockRevision.objects.filter(
        block__in=blocks, created_at__gt=since
    ).order_by("created_at"):
        read.setdefault(revision.block_id, revision.previous_text)
    return {b.block_id for b in blocks if b.id in read and read[b.id] != b.text}


def _segments(text: str, notes: list[dict]) -> list[dict]:
    """The block's text cut around the quotes it holds; overlapping quotes keep the first."""

    segments, cursor = [], 0
    for note in sorted((n for n in notes if n["span"]), key=lambda n: n["span"]):
        start, end = note["span"]
        if start < cursor:
            continue
        if start > cursor:
            segments.append({"text": text[cursor:start], "note": None})
        segments.append({"text": text[start:end], "note": note})
        cursor = end
    if cursor < len(text):
        segments.append({"text": text[cursor:], "note": None})
    return segments


def attach_notes(edition, chapter, rows: list[dict], analysis: dict | None = None) -> dict:
    """Give each reader row its cards, text segments and window heading; return the chapter's."""

    from almonium_book_processor.catalog.adaptation_quality import adaptation_quality
    from almonium_book_processor.catalog.difficulty_panel import difficulty_panel

    analysis = analysis if analysis is not None else analysis_context(edition)
    reading, read_at, current = _reading(edition, chapter, analysis)
    if reading is None:
        return {"available": False, "count": 0}
    if current:
        # The gate's level and the judges belong to the edition as it stands.
        analysis.update(adaptation_quality(edition, analysis))
        panel = difficulty_panel(analysis)
    else:
        panel = difficulty_panel({"chapter_projections": [reading]})
    chapter_row = next(r for r in panel["rows"] if r["chapter"].id == chapter.id)
    windows = chapter_row["windows"]
    changed = _changed_blocks([row["block"] for row in rows if row["block"]], read_at)

    # Where each window starts: the analysis's own cut of the current text, or, when the
    # text has moved so far that the cut no longer gives as many windows, the first block
    # each window cites.
    parts = window_parts(chapter_blocks(chapter), analysis_spec(edition.language)["window_bytes"])
    order = {row["block"].block_id: i for i, row in enumerate(rows) if row["block"]}
    starts = {}
    if len(parts) == len(windows):
        for window, part in zip(windows, parts, strict=True):
            starts[part[0]["block_id"]] = window
    else:
        for window in windows:
            cited = [
                e["block_id"]
                for e in window["evidence"] + window["more_evidence"]
                if e["block_id"] in order
            ]
            if cited:
                starts.setdefault(min(cited, key=order.get), window)

    texts = {row["block"].block_id: row["block"].text for row in rows if row["block"]}
    notes_by_block: dict[str, list[dict]] = {}
    count = 0
    for window in windows:
        for item in window["evidence"] + window["more_evidence"]:
            text = texts.get(item["block_id"])
            if text is None:
                continue
            span = _locate(text, item.get("quote", "")) if item["block_id"] not in changed else None
            notes_by_block.setdefault(item["block_id"], []).append(
                {
                    **item,
                    "kind": "content" if item["dimension"].lower() == "content" else "evidence",
                    "span": span,
                    "changed": span is None or item["block_id"] in changed,
                    "window": window["number"],
                }
            )
            count += 1
    index = 0
    for row in rows:
        block = row["block"]
        if not block:
            continue
        notes = sorted(
            notes_by_block.get(block.block_id, []),
            key=lambda n: n["span"] or (len(block.text), 0),
        )
        for note in notes:
            note["index"] = index
            index += 1
        row["notes"] = notes
        row["note_segments"] = _segments(block.text, notes) if notes else None
        row["notes_window"] = starts.get(block.block_id)
        row["short_id"] = block.block_id.rsplit(".", 1)[-1]
    return {
        "available": True,
        "current": current,
        "count": count,
        "level": chapter_row["level"],
        "above": chapter_row["above"],
        "above_ungated": chapter_row["above_ungated"],
        "within_target": chapter_row["within_target"],
        "judges": chapter_row["judges"],
        "windows": len(windows),
    }
