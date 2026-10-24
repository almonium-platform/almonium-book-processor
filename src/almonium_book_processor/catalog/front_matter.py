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
# A roman numeral is a well-formed one and the whole first word: "CIVIL WAR" and "DIM" are
# words, not chapter numbers (ELTeC's The Hosts of the Lord lost 26 chapters to "CIVIL").
ROMAN = re.compile(r"^m{0,3}(cm|cd|d?c{0,3})(xc|xl|l?x{0,3})(ix|iv|v?i{0,3})$", re.IGNORECASE)
LABELLED = re.compile(
    r"^\W*(chapter|chapitre|kapitel|capitolo|capítulo|глава|розділ|letter|lettre|brief"
    r"|book|livre|buch|part|partie|teil|частина|\d+\b)",
    re.IGNORECASE,
)


def _is_numbered(title: str) -> bool:
    """Whether a title opens with a chapter number: a label word, digits, or a roman numeral."""

    title = title.strip()
    if LABELLED.match(title):
        return True
    first = re.split(r"[\s.:;,\-–—)\]]+", title.lstrip("([-–— "), maxsplit=1)[0] if title else ""
    return bool(first) and bool(ROMAN.match(first))


# What sits around a story, in the languages the library makes books in.
MATTER = re.compile(
    r"\b(preface|préface|prefazione|prefacio|pr[óo]logo|vorwort|vorrede|avant-propos|передмова"
    r"|foreword|introdu\w*|einleitung|einführung|вступ|dedication|dédicace|dedica|dedicatoria"
    r"|widmung|zueignung|присвята|contents|table des matières|sommaire|inhalt(sverzeichnis)?"
    r"|[íi]ndice|зміст|illustrations?|afterword|nachwort|післямова|appendix|appendice|anhang"
    r"|додаток"
    r"|notes?|notas?|anmerkungen|przypisy|примітки|avvertenza|advertencia|glossary|glossaire|glossar"
    r"|глосарій|bibliography|bibliographie|бібліографія|acknowledg\w*|transcriber"
    r"|about the author|über den autor|про автора|colophon|advertisements?|errata"
    r"|there are several editions of this ebook)\b",
    re.IGNORECASE,
)

# A closing word is the whole title, so "LA FIN DU MONDE" stays a story title.
CLOSING = re.compile(r"^\W*(fin|fine|the end|ende|finis|конец|кінець)\W*$", re.IGNORECASE)


def chapter_roles(
    titles: list[str],
    *,
    book_title: str | None = None,
    author: str | None = None,
    cut_by_size: set[int] | frozenset[int] = frozenset(),
) -> list[str]:
    """A role per chapter title, in order: front matter, the story, back matter.

    The story runs from the first to the last chapter with a story title: a numbered one, or
    any title that is not a word for the matter around a book. Untitled chapters and
    prefaces before the story are front matter, notes after it back matter. An untitled
    chapter inside the story is the story's. A book with no story title is all story.

    When the book numbers its chapters, the story begins at the first numbered one: the
    publisher's pages before it carry titles that are no word for matter ("OEUVRES DE
    VOLTAIRE", "CANDIDE, OU L'OPTIMISME" on Candide's title pages), and they would otherwise
    count as the story and be held to its level.
    """

    # a part of a text that ingest cut by size is the story, whatever it is called:
    # Damiano's untitled parts stood before any title the rules would take for the story
    story = [index in cut_by_size or _is_story(title) for index, title in enumerate(titles)]
    # the title page: chapters named after the book itself or its author, ahead of the story
    for index, title in enumerate(titles):
        if (
            story[index]
            and index not in cut_by_size
            and any(_same_title(title, name) for name in (book_title, author) if name)
        ):
            story[index] = False
        elif story[index]:
            break
    untitled = [
        not title.strip() and index not in cut_by_size for index, title in enumerate(titles)
    ]
    if not any(story):
        # Venus im Pelz: a title page, a "Vorwort" and the text cut by size into untitled
        # parts: the parts are the story, the titled pages the matter around it
        if any(untitled) and not all(untitled):
            story = untitled
        else:
            return [Chapter.AnalysisRole.BODY] * len(titles)
    # a title page is not a numbered chapter, whatever its letters look like ("D R A C U L A")
    numbered = [story[index] and _is_numbered(title) for index, title in enumerate(titles)]
    first = numbered.index(True) if any(numbered) else story.index(True)
    if cut_by_size:
        first = min(first, min(index for index in cut_by_size if index < len(titles)))
    # an untitled chapter after the last titled one is the story's too: Damiano's last file is
    # 170,000 characters of story cut by size into untitled parts
    story_or_untitled = [story[i] or (untitled[i] and i > first) for i in range(len(titles))]
    last = len(titles) - 1 - story_or_untitled[::-1].index(True)
    roles = [
        Chapter.AnalysisRole.FRONT
        if index < first
        else Chapter.AnalysisRole.BACK
        if index > last
        else Chapter.AnalysisRole.BODY
        for index in range(len(titles))
    ]
    # a contents, notes or preface page inside the story's span is still matter: Dracula's
    # "Contents" sat between its title page and its first chapter
    for index, title in enumerate(titles):
        if roles[index] == Chapter.AnalysisRole.BODY and _is_matter(title):
            roles[index] = (
                Chapter.AnalysisRole.FRONT
                if index < (first + last) / 2
                else Chapter.AnalysisRole.BACK
            )
    return roles


def _is_matter(title: str) -> bool:
    title = title.strip()
    return bool(title) and (
        bool(CLOSING.match(title)) or (not _is_numbered(title) and bool(MATTER.search(title)))
    )


def _same_title(title: str, book_title: str) -> bool:
    """Whether a chapter title is the book's own, as a title page carries it."""

    plain = lambda text: re.sub(r"[^\w]+", "", text).lower()  # noqa: E731  "D R A C U L A" is Dracula
    chapter, book = plain(title), plain(book_title)
    return bool(chapter) and (
        chapter == book or book.startswith(chapter) or chapter.startswith(book)
    )


def _is_story(title: str) -> bool:
    title = title.strip()
    if not title:
        return False
    if CLOSING.match(title):
        return False
    return _is_numbered(title) or not MATTER.search(title)


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
        roles = chapter_roles(
            [chapter.title for chapter in chapters], book_title=edition.title, author=edition.author
        )
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
