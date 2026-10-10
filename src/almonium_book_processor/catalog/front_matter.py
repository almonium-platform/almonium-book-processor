"""Which chapters are the story, and which the matter around it.

The level gate, the book estimate and the probe read the substantive chapters: a title page,
a dedication poem or an author's preface is adapted as far as it goes and must not close a
level for the story. Nobody tags chapters by hand. The roles are read off the chapter titles
when a source is ingested and copied to every edition made from it.
"""

from __future__ import annotations

import contextlib
import re

from almonium_book_processor.catalog.models import Chapter, Edition

# A numbered title is a chapter of the story whatever word follows the number: Wells calls
# the first chapter of The Time Machine "I Introduction".
NUMBERED = re.compile(
    r"^\W*(chapter|chapitre|kapitel|capitolo|capítulo|глава|розділ|letter|lettre|brief"
    r"|book|livre|buch|part|partie|teil|частина|[ivxlcdm]+\b|\d+\b)",
    re.IGNORECASE,
)
# What sits around a story, in the languages the library makes books in.
MATTER = re.compile(
    r"\b(preface|préface|vorwort|передмова|foreword|introduction|einleitung|einführung"
    r"|вступ|dedication|dédicace|widmung|присвята|contents|table des matières|inhalt|зміст"
    r"|afterword|nachwort|післямова|appendix|appendice|anhang|додаток|notes?|anmerkungen"
    r"|примітки|glossary|glossaire|glossar|глосарій|bibliography|bibliographie|бібліографія"
    r"|acknowledg\w*|transcriber|about the author|über den autor|про автора|colophon"
    r"|advertisements?|errata)\b",
    re.IGNORECASE,
)


def chapter_roles(titles: list[str]) -> list[str]:
    """A role per chapter title, in order: front matter, the story, back matter.

    The story runs from the first to the last chapter with a story title: a numbered one, or
    any title that is not a word for the matter around a book. Untitled chapters and
    prefaces before the story are front matter, notes after it back matter. An untitled
    chapter inside the story is the story's. A book with no story title is all story.
    """

    story = [_is_story(title) for title in titles]
    if not any(story):
        return [Chapter.AnalysisRole.BODY] * len(titles)
    first = story.index(True)
    last = len(story) - 1 - story[::-1].index(True)
    return [
        Chapter.AnalysisRole.FRONT
        if index < first
        else Chapter.AnalysisRole.BACK
        if index > last
        else Chapter.AnalysisRole.BODY
        for index in range(len(titles))
    ]


def _is_story(title: str) -> bool:
    title = title.strip()
    if not title:
        return False
    return bool(NUMBERED.match(title)) or not MATTER.search(title)


def source_role(edition: Edition, sequence: int) -> str:
    """The role of the source's chapter of this sequence, for an edition made from it."""

    role = edition.source_edition.chapters.filter(sequence=sequence).values_list(
        "analysis_role", flat=True
    )
    return role.first() or Chapter.AnalysisRole.BODY


def retag(edition: Edition) -> int:
    """Set the edition's chapter roles afresh; returns how many chapters changed.

    An original is read from its titles; an edition made from a source copies the source's.
    A changed role retires the edition's book projection and, where the text has been read,
    has it recomputed from the readings: no judge reads again.
    """

    from almonium_book_processor.catalog.chapter_projections import KINDS, queue_projection_refresh

    chapters = list(edition.chapters.order_by("sequence"))
    if edition.source_edition_id:
        roles = [source_role(edition, chapter.sequence) for chapter in chapters]
    else:
        roles = chapter_roles([chapter.title for chapter in chapters])
    changed = [
        chapter
        for chapter, role in zip(chapters, roles, strict=True)
        if chapter.analysis_role != role and not setattr(chapter, "analysis_role", role)
    ]
    if changed:
        Chapter.objects.bulk_update(changed, ["analysis_role"])
        edition.artifacts.filter(kind=KINDS[0], chapter__isnull=True, is_current=True).update(
            is_current=False
        )
        # not read yet: the first reading projects it
        with contextlib.suppress(ValueError):
            queue_projection_refresh(str(edition.id))
    return len(changed)
