"""The editorial catalogue, grouped by work.

The unit of the catalogue is the work, not the edition. Four Frankenstein cards
in a grid make an editor read titles to find out that two of them are the same
book; one panel per work with an edition row inside says it at a glance. Rows
sit in the order an editor reads a parallel tree: the canonical original, then
the parallel editions by language, then the standalone ones. Works are ordered
by the most urgent status inside them, so the panel that needs a person comes
first, and by author surname after that.

User imports are the other list. A private import is always one edition per
work and the owner is what an operator scans for, so there is nothing to
group: one flat table, newest upload first, in the same row grammar.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from django.db.models import Count, Q
from django.utils import timezone

from almonium_book_processor.catalog.models import Edition, PipelineRun, QAWarning, Work
from almonium_book_processor.catalog.release_state import PromotionToken

# Most urgent first. Failed and review need a person; processing and queued
# need time; draft needs an upload to finish; ready and published need nothing.
STATUS_URGENCY: tuple[str, ...] = (
    Edition.Status.FAILED,
    Edition.Status.REVIEW,
    Edition.Status.PROCESSING,
    Edition.Status.QUEUED,
    Edition.Status.DRAFT,
    Edition.Status.READY,
    Edition.Status.PUBLISHED,
)

# Statuses a work's rollup does not mention: nothing is waiting on anyone.
SETTLED_STATUSES = frozenset({Edition.Status.READY, Edition.Status.PUBLISHED})

# Statuses the rollup reports as "processing" in muted text rather than a pill.
IN_FLIGHT_STATUSES = frozenset({Edition.Status.PROCESSING, Edition.Status.QUEUED})

ROLE_ORDER: tuple[str, ...] = (
    Edition.ParallelRole.CANONICAL,
    Edition.ParallelRole.PARALLEL,
    Edition.ParallelRole.STANDALONE,
)

# Inside a work panel the word "edition" is implied by the row, so the role
# reads as one word. The edition page keeps the model's long form.
SHORT_ROLE_LABELS = {
    Edition.ParallelRole.CANONICAL: "Canonical",
    Edition.ParallelRole.PARALLEL: "Parallel",
    Edition.ParallelRole.STANDALONE: "Standalone",
}


def word_count_label(count: int) -> str:
    """A word count as the catalogue prints it: thousands spaced, unit named."""

    number = f"{count:,}".replace(",", "\u202f")
    return f"{number} word" if count == 1 else f"{number} words"


def warning_count_label(count: int) -> str:
    return f"{count} warning" if count == 1 else f"{count} warnings"


@dataclass
class EditionRow:
    edition: Edition
    # The edition's own title, or None when it is the work's and would repeat
    # the panel header. A parallel translation still waiting for its name is
    # the empty string, which the template renders as "Title pending".
    title: str | None
    type_label: str
    role_label: str
    warning_count: int
    # The language this edition is generated from, when it is a block-for-block
    # translation whose word count is really its source's.
    source_language: str | None
    # The run that is working on this edition right now, if any; the row draws
    # the stage and its progress in place of a status pill.
    run: PipelineRun | None
    # Whether Almonium here still shows this edition's previous metadata.
    metadata_behind: bool = False
    # One token per promotion target, in target order, once the edition is
    # approved or has been promoted; empty before that.
    promotions: list[PromotionToken] = field(default_factory=list)

    @property
    def status(self) -> str:
        return self.edition.status

    @property
    def status_label(self) -> str:
        return self.edition.get_status_display()

    @property
    def language(self) -> str:
        return self.edition.language.upper()

    @property
    def role(self) -> str:
        return self.edition.parallel_role

    @property
    def cefr_level(self) -> str | None:
        return self.edition.cefr_level

    @property
    def words_label(self) -> str:
        if self.source_language:
            return f"from {self.source_language}"
        return word_count_label(self.edition.word_count)

    @property
    def warnings_label(self) -> str:
        return warning_count_label(self.warning_count)

    @property
    def warnings_urgent(self) -> bool:
        """Whether the warning count is the reason this row needs opening."""

        return self.warning_count > 0 and self.edition.status in {
            Edition.Status.REVIEW,
            Edition.Status.FAILED,
        }

    @property
    def needs_review(self) -> bool:
        return self.edition.status == Edition.Status.REVIEW

    @property
    def is_failed(self) -> bool:
        return self.edition.status == Edition.Status.FAILED


@dataclass
class Rollup:
    """What a work panel says about its editions at the right end of its header.

    A pill for the worst status that is waiting on a person, muted text when
    the worst thing happening is that a run is still going, and nothing when
    every edition is ready or published.
    """

    status: str
    count: int

    @property
    def in_flight(self) -> bool:
        return self.status in IN_FLIGHT_STATUSES

    @property
    def label(self) -> str:
        if self.in_flight:
            return f"{self.count} processing"
        return f"{self.count} {Edition.Status(self.status).label.lower()}"


@dataclass
class PromotionRollup:
    """One promotion sentence for a work header or the page subtitle.

    Only behind and failed are worth a sentence: current is the quiet state
    and never promoted is what a hollow ring on the row already says.
    """

    state: str
    target: str
    count: int

    @property
    def label(self) -> str:
        return f"{self.count} {self.state} on {self.target}"


def promotion_rollups(rows: list[EditionRow]) -> list[PromotionRollup]:
    """Failed first, then behind, each per target in target order."""

    counts: dict[tuple[str, str], int] = {}
    for row in rows:
        for token in row.promotions:
            if token.state in ("failed", "behind"):
                key = (token.state, token.target)
                counts[key] = counts.get(key, 0) + 1
    order = {"failed": 0, "behind": 1}
    return [
        PromotionRollup(state=state, target=target, count=count)
        for (state, target), count in sorted(counts.items(), key=lambda item: order[item[0][0]])
    ]


@dataclass
class WorkGroup:
    work: Work
    rows: list[EditionRow] = field(default_factory=list)
    # What this environment's ledger says the work's model calls cost.
    spend_label: str = ""

    @property
    def title(self) -> str:
        return self.work.title

    @property
    def author(self) -> str:
        return self.work.author

    @property
    def edition_count_label(self) -> str:
        count = len(self.rows)
        return f"{count} edition" if count == 1 else f"{count} editions"

    @property
    def urgency(self) -> int:
        return min(STATUS_URGENCY.index(row.status) for row in self.rows)

    @property
    def rollup(self) -> Rollup | None:
        open_statuses = [row.status for row in self.rows if row.status not in SETTLED_STATUSES]
        if not open_statuses:
            return None
        worst = min(open_statuses, key=STATUS_URGENCY.index)
        if worst in IN_FLIGHT_STATUSES:
            count = sum(1 for status in open_statuses if status in IN_FLIGHT_STATUSES)
        else:
            count = open_statuses.count(worst)
        return Rollup(status=worst, count=count)

    @property
    def promotion_rollups(self) -> list[PromotionRollup]:
        return promotion_rollups(self.rows)


@dataclass
class CatalogueSummary:
    work_count: int
    edition_count: int
    failed: int
    review: int
    processing: int
    promotions: list[PromotionRollup] = field(default_factory=list)

    @property
    def label(self) -> str:
        parts = [
            f"{self.work_count} work" if self.work_count == 1 else f"{self.work_count} works",
            (
                f"{self.edition_count} edition"
                if self.edition_count == 1
                else f"{self.edition_count} editions"
            ),
        ]
        if self.failed:
            parts.append(f"{self.failed} failed")
        if self.review:
            parts.append(f"{self.review} needs review")
        if self.processing:
            parts.append(f"{self.processing} processing")
        parts.extend(rollup.label for rollup in self.promotions)
        return " · ".join(parts)


def _surname(author: str) -> str:
    parts = author.split()
    return parts[-1].casefold() if parts else ""


def _active_runs(visibility: str) -> dict:
    """The newest queued or running run per edition, keyed by edition id."""

    runs: dict = {}
    active = PipelineRun.objects.filter(
        status__in=[PipelineRun.Status.QUEUED, PipelineRun.Status.RUNNING],
        edition__work__visibility=visibility,
    ).order_by("-created_at")
    for run in active:
        runs.setdefault(run.edition_id, run)
    return runs


def _editions(visibility: str):
    return (
        Edition.objects.filter(work__visibility=visibility)
        .select_related("work", "source_edition")
        .annotate(
            warning_count=Count(
                "warnings",
                filter=Q(
                    warnings__severity__in=[
                        QAWarning.Severity.WARNING,
                        QAWarning.Severity.ERROR,
                    ],
                    warnings__resolved_at__isnull=True,
                ),
                distinct=True,
            )
        )
    )


def _row(edition: Edition, run: PipelineRun | None) -> EditionRow:
    work_title = edition.work.title
    title = edition.title
    return EditionRow(
        edition=edition,
        title=None if title and title == work_title else title,
        type_label=edition.get_edition_type_display(),
        role_label=SHORT_ROLE_LABELS[edition.parallel_role],
        warning_count=edition.warning_count,
        source_language=(
            edition.source_edition.language.upper() if edition.is_parallel_translation else None
        ),
        run=run,
    )


def catalogue_groups(visibility: str) -> list[WorkGroup]:
    """Every work of the given visibility with its editions as rows."""

    from almonium_book_processor.catalog.release_state import listing_release_state

    runs = _active_runs(visibility)
    editions = list(_editions(visibility))
    release = listing_release_state(editions)
    groups: dict = {}
    for edition in editions:
        group = groups.setdefault(edition.work_id, WorkGroup(work=edition.work))
        row = _row(edition, runs.get(edition.id))
        state = release[edition.id]
        row.metadata_behind = state.metadata_behind
        row.promotions = state.tokens
        group.rows.append(row)
    from almonium_book_processor.catalog.spend import spend_by_work

    spend = spend_by_work([group.work for group in groups.values()])
    for group in groups.values():
        group.rows.sort(key=lambda row: (ROLE_ORDER.index(row.role), row.edition.language))
        group.spend_label = spend.get(group.work.id, "")
    return sorted(
        groups.values(),
        key=lambda group: (group.urgency, _surname(group.work.author), group.title.casefold()),
    )


def catalogue_summary(groups: list[WorkGroup]) -> CatalogueSummary:
    rows = [row for group in groups for row in group.rows]
    return CatalogueSummary(
        work_count=len(groups),
        edition_count=len(rows),
        failed=sum(1 for row in rows if row.status == Edition.Status.FAILED),
        review=sum(1 for row in rows if row.status == Edition.Status.REVIEW),
        processing=sum(1 for row in rows if row.status in IN_FLIGHT_STATUSES),
        promotions=promotion_rollups(rows),
    )


SOURCE_FORMATS = {".epub": "EPUB", ".xml": "TEI"}


def source_format(edition: Edition) -> str:
    """EPUB or TEI, from the uploaded file's extension; blank when there is none."""

    if not edition.source_file:
        return ""
    return SOURCE_FORMATS.get(Path(edition.source_file.name).suffix.lower(), "")


def uploaded_label(moment) -> str:
    """When an import arrived, as an operator reads it: today by time, else by date."""

    local = timezone.localtime(moment)
    if local.date() == timezone.localdate():
        return f"Today, {local:%H:%M}"
    return f"{local:%b} {local.day}, {local:%H:%M}"


@dataclass
class ImportRow(EditionRow):
    """One user import: the same row grammar as the catalogue, plus its owner."""

    @property
    def status_label(self) -> str:
        # A ready import is released to its owner rather than published.
        if self.edition.status == Edition.Status.READY:
            return "Available"
        return self.edition.get_status_display()

    @property
    def author(self) -> str:
        return self.edition.author

    @property
    def source_format(self) -> str:
        return source_format(self.edition)

    @property
    def owner_label(self) -> str:
        label = self.edition.work.owner_label
        return f"@{label}" if label else ""

    @property
    def owner_id(self) -> str:
        return str(self.edition.work.owner_id or "")

    @property
    def owner_id_short(self) -> str:
        owner_id = self.edition.work.owner_id
        if owner_id is None:
            return ""
        return f"{owner_id.hex[:4]}\u2026{owner_id.hex[-4:]}"

    @property
    def uploaded_label(self) -> str:
        return uploaded_label(self.edition.created_at)


def import_rows(visibility: str = Work.Visibility.PRIVATE) -> list[ImportRow]:
    """Every user import as a flat list, newest upload first."""

    runs = _active_runs(visibility)
    rows = []
    for edition in _editions(visibility).order_by("-created_at"):
        row = _row(edition, runs.get(edition.id))
        rows.append(
            ImportRow(
                edition=row.edition,
                title=edition.title,
                type_label=row.type_label,
                role_label=row.role_label,
                warning_count=row.warning_count,
                source_language=row.source_language,
                run=row.run,
            )
        )
    return rows
