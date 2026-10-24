"""The shape of a source as ingest would cut it, judged without storing or spending a cent.

Wrong splits show up only at scale: on 24 October 2026, 12 of 86 ingested originals had three
body chapters or fewer, one of them A Christmas Carol in two pieces of which one was 91% of the
book, and 18 counted the Gutenberg preamble as a body chapter. Every one of these is visible in
the chapter sizes and titles before any judge reads a word. ``measure`` takes an ingest's
artifact and ``judge`` says whether the shape is sound; the shake-down command runs both over
books it never keeps, and an ingest can ask the same of what it is about to store.
"""

from __future__ import annotations

import re
import statistics
from typing import Any

from almonium_book_processor.catalog.front_matter import chapter_roles
from almonium_book_processor.models import BlockType, BookArtifact

# A book this long cut into this few pieces was not cut at its chapters.
LONG_BOOK_CHARS = 60_000
FEW_CHAPTERS = 2  # Die Verwandlung and Heart of Darkness are three parts, rightly
# One body chapter holding this share of the body text, among several, is a missed heading.
LOPSIDED_SHARE = 0.40
# A body chapter shorter than this is a heading that caught little text; a few are a book's
# own short sections (Zarathustra's aphorisms), this share of them is a cut gone wrong.
TINY_CHAPTER_CHARS = 400
TINY_CHAPTER_SHARE = 0.25
# Titles of pages that are matter around a book and never the story; ingest should see them.
MATTER_TITLES = re.compile(
    r"^\s*(contents|table of contents|illustrations|list of illustrations|inhalt(sverzeichnis)?|"
    r"table des mati[eè]res|[íi]ndice|indice|sommaire|note|notes|preface|pr[ée]face|vorwort|"
    r"pr[óo]logo|prefazione|introduction|einleitung|introducci[óo]n|introduzione|"
    r"transcriber'?s note|there are several editions of this ebook.*)\s*\.?$",
    re.IGNORECASE,
)


def measure(artifact: BookArtifact) -> dict[str, Any]:
    """What ingest would store of this book, in numbers: chapters, their roles, sizes, titles."""

    chapters: dict[int, dict[str, Any]] = {}
    for block in artifact.blocks:
        chapter = chapters.setdefault(block.chapter, {"title": "", "chars": 0})
        if block.type == BlockType.HEADING and not chapter["title"]:
            if not block.attributes.get("part"):
                chapter["title"] = block.text.strip()
        elif block.type not in (BlockType.IMAGE, BlockType.SEPARATOR):
            chapter["chars"] += len(block.text)
    ordered = [chapters[sequence] for sequence in sorted(chapters)]
    roles = chapter_roles(
        [chapter["title"] for chapter in ordered],
        book_title=artifact.edition.title,
        author=artifact.edition.author,
    )
    for chapter, role in zip(ordered, roles, strict=True):
        chapter["role"] = role
    body = [chapter for chapter in ordered if chapter["role"] == "body"]
    body_chars = sum(chapter["chars"] for chapter in body)
    return {
        "chapters": len(ordered),
        "body_chapters": len(body),
        "chars": sum(chapter["chars"] for chapter in ordered),
        "body_chars": body_chars,
        "largest_body_share": (
            round(max(chapter["chars"] for chapter in body) / body_chars, 3)
            if body and body_chars
            else None
        ),
        "median_body_chars": int(statistics.median(c["chars"] for c in body)) if body else None,
        "tiny_body_chapters": sum(1 for c in body if c["chars"] < TINY_CHAPTER_CHARS),
        "first_sequence": min(chapters) if chapters else None,
        "first_role": ordered[0]["role"] if ordered else None,
        "matter_titles_in_body": [
            chapter["title"][:60]
            for chapter in body
            if chapter["title"] and MATTER_TITLES.match(chapter["title"])
        ],
        "titles": [chapter["title"][:60] for chapter in ordered[:40]],
        "warnings": sorted({warning.code for warning in artifact.warnings}),
        "language": artifact.edition.language,
    }


def judge(metrics: dict[str, Any]) -> tuple[str, list[str]]:
    """``("ok", [])`` or ``("suspect", reasons)``: whether ingest would cut this book right."""

    reasons = []
    body, chars = metrics["body_chapters"], metrics["chars"]
    if body == 0:
        reasons.append("no body chapter")
    if chars >= LONG_BOOK_CHARS and 0 < body <= FEW_CHAPTERS:
        reasons.append(f"{chars:,} characters in {body} body chapter(s)")
    if body > FEW_CHAPTERS and (metrics["largest_body_share"] or 0) > LOPSIDED_SHARE:
        reasons.append(f"one body chapter is {metrics['largest_body_share']:.0%} of the body")
    if metrics["matter_titles_in_body"]:
        reasons.append(
            "matter pages counted as body: " + ", ".join(metrics["matter_titles_in_body"][:3])
        )
    tiny = metrics["tiny_body_chapters"]
    if body and tiny / body > TINY_CHAPTER_SHARE:
        reasons.append(f"{tiny} of {body} body chapters under {TINY_CHAPTER_CHARS} characters")
    return ("suspect" if reasons else "ok"), reasons
