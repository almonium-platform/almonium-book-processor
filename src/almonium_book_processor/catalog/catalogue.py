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
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from django.db.models import Count, Max, Q
from django.utils import timezone

from almonium_book_processor.catalog.models import Edition, PipelineRun, QAWarning, Work
from almonium_book_processor.catalog.release_state import PromotionToken
from almonium_book_processor.languages import LANGUAGES

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


def twin_ids(editions) -> set:
    """Editions of one work that share a language, an edition type and a level with another.

    Two Ukrainian machine translations of the same book read alike in every
    list, title included, so each list names them by slug instead. A B1 and a
    B2 adaptation already differ by their level chip.
    """

    seen: dict[tuple, list] = {}
    for edition in editions:
        key = (edition.work_id, edition.language, edition.edition_type, edition.cefr_level)
        seen.setdefault(key, []).append(edition.id)
    return {edition_id for ids in seen.values() if len(ids) > 1 for edition_id in ids}


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
    # The level an adaptation without a level of its own was generated for.
    target_level: str | None = None
    # The stage whose run failed, on a failed edition.
    failed_stage: str = ""
    # Whether another edition of the work has this one's language, type and level,
    # so the row names its slug to tell them apart.
    twin: bool = False

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
    def level_label(self) -> str | None:
        """The level chip: the edition's own level, or "B1 target" for an adaptation."""

        if self.cefr_level:
            return self.cefr_level
        return f"{self.target_level} target" if self.target_level else None

    @property
    def token_level(self) -> str:
        """The level on the edition strip, where "target" would not fit."""

        return self.cefr_level or self.target_level or ""

    @property
    def is_canonical(self) -> bool:
        return self.role == Edition.ParallelRole.CANONICAL

    @property
    def token_state(self) -> str:
        """The status dot's colour: settled, review, failed, or a run in flight."""

        if self.run or self.status in IN_FLIGHT_STATUSES:
            return "processing"
        if self.status in SETTLED_STATUSES:
            return "settled"
        return self.status

    @property
    def token_title(self) -> str:
        """What a hover over the strip token says: type, role, status, stage."""

        parts = [self.type_label, self.role_label, self.status_label]
        if self.twin:
            parts.insert(0, self.edition.slug)
        if self.run:
            parts.append(self.run.get_stage_display())
        elif self.failed_stage:
            parts.append(f"at {self.failed_stage}")
        return " · ".join(parts)

    @property
    def words_label(self) -> str:
        if self.failed_stage:
            return f"Failed at {self.failed_stage[0].lower()}{self.failed_stage[1:]}"
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
        if self.status == Edition.Status.REVIEW and self.count != 1:
            return f"{self.count} need review"
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

    @property
    def button_label(self) -> str:
        return f"Promote {self.count} to {self.target}"


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
    spend_usd: Decimal = Decimal("0")
    # The latest run or edit on any of its editions.
    last_activity: datetime | None = None
    # Whether the catalogue's filter found this work through one of its
    # editions rather than its own title or author, so it opens expanded.
    matched_through_edition: bool = False

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

    @property
    def needs_attention(self) -> bool:
        return any(row.is_failed or row.needs_review for row in self.rows)

    @property
    def processing(self) -> bool:
        return any(row.run or row.status in IN_FLIGHT_STATUSES for row in self.rows)

    def behind_count(self, target: str) -> int:
        return sum(
            1
            for row in self.rows
            if any(t.target == target and t.state in ("behind", "failed") for t in row.promotions)
        )


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
            parts.append(f"{self.review} {'needs' if self.review == 1 else 'need'} review")
        if self.processing:
            parts.append(f"{self.processing} processing")
        parts.extend(rollup.label for rollup in self.promotions)
        return " · ".join(parts)

    @property
    def promotable(self) -> list[PromotionRollup]:
        """One button's worth per target: everything behind or failed there, as one count.

        A failed promotion leaves the target behind too, so the button that
        catches a target up counts both and its title says how many of each.
        """

        counts: dict[str, int] = {}
        for rollup in self.promotions:
            counts[rollup.target] = counts.get(rollup.target, 0) + rollup.count
        return [
            PromotionRollup(state="behind", target=target, count=count)
            for target, count in counts.items()
        ]


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
    failed_stages = _failed_stages(
        [edition.id for edition in editions if edition.status == Edition.Status.FAILED]
    )
    last_runs = dict(
        PipelineRun.objects.filter(edition__work__visibility=visibility)
        .values_list("edition_id")
        .annotate(Max("created_at"))
    )
    twins = twin_ids(editions)
    for edition in editions:
        group = groups.setdefault(edition.work_id, WorkGroup(work=edition.work))
        row = _row(edition, runs.get(edition.id))
        row.twin = edition.id in twins
        state = release[edition.id]
        row.metadata_behind = state.metadata_behind
        row.promotions = state.tokens
        row.failed_stage = failed_stages.get(edition.id, "")
        if edition.edition_type == Edition.EditionType.ADAPTATION and not edition.cefr_level:
            from almonium_book_processor.catalog.adaptation_quality import adaptation_target

            row.target_level = adaptation_target(edition)
        group.rows.append(row)
        moments = [edition.updated_at, last_runs.get(edition.id)]
        group.last_activity = max(
            [moment for moment in [group.last_activity, *moments] if moment is not None]
        )
    from almonium_book_processor.catalog.spend import format_usd, spend_totals_by_work

    spend = spend_totals_by_work([group.work for group in groups.values()])
    for group in groups.values():
        group.rows.sort(key=lambda row: (ROLE_ORDER.index(row.role), row.edition.language))
        if group.work.id in spend:
            group.spend_usd = spend[group.work.id]
            group.spend_label = format_usd(group.spend_usd)
    return sorted(
        groups.values(),
        key=lambda group: (group.urgency, _surname(group.work.author), group.title.casefold()),
    )


def _failed_stages(edition_ids) -> dict:
    """The stage of the newest failed run of each failed edition, as the row names it."""

    stages: dict = {}
    failed = PipelineRun.objects.filter(
        edition_id__in=edition_ids, status=PipelineRun.Status.FAILED
    ).order_by("-created_at")
    for run in failed:
        stages.setdefault(run.edition_id, run.get_stage_display())
    return stages


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


# The catalogue at scale: one collapsed row per work, filtered by a tab, sorted,
# searched and paged, every choice in the URL so a link reopens the same list.

PAGE_SIZE = 25
DEFAULT_TAB = "attention"
DEFAULT_SORT = "urgent"

SORTS: dict[str, tuple[str, str]] = {
    # key: (the select's label, how the line under the tabs restates it)
    "urgent": ("Most urgent", "most urgent first"),
    "updated": ("Recently updated", "recently updated first"),
    "newest": ("Newest", "newest first"),
    "title": ("Title", "by title"),
    "author": ("Author", "by author"),
    "spend": ("AI spend", "highest AI spend first"),
}


LANGUAGE_NAMES = {language.code: language.name for language in LANGUAGES}


def language_name(code: str) -> str:
    return LANGUAGE_NAMES.get(code, code.upper())


def _plural(count: int, singular: str, plural: str | None = None) -> str:
    return f"{count} {singular if count == 1 else plural or singular + 's'}"


def _sort_key(sort: str):
    def recency(group: WorkGroup) -> float:
        return -group.last_activity.timestamp() if group.last_activity else 0.0

    def title(group: WorkGroup) -> str:
        return group.title.casefold()

    keys = {
        "urgent": lambda group: (group.urgency, recency(group), title(group)),
        "updated": lambda group: (recency(group), title(group)),
        "newest": lambda group: (-group.work.created_at.timestamp(), title(group)),
        "title": title,
        "author": lambda group: (_surname(group.author), title(group)),
        "spend": lambda group: (-group.spend_usd, title(group)),
    }
    return keys[sort]


@dataclass
class CatalogueTab:
    key: str
    label: str
    count: int
    unit: str
    url: str
    active: bool

    @property
    def count_label(self) -> str:
        # The active tab names what it counts; the others are a bare number.
        return _plural(self.count, self.unit) if self.active else str(self.count)


@dataclass
class CataloguePage:
    """One page of the public catalogue as its query asks for it."""

    tab: str
    sort: str
    language: str
    search: str
    page: int
    tabs: list[CatalogueTab]
    groups: list[WorkGroup]
    matched: int
    breakdown: str
    summary: CatalogueSummary
    languages: list[tuple[str, str]]
    more_url: str = ""
    more_count: int = 0

    @property
    def sorts(self) -> list[tuple[str, str]]:
        return [(key, label) for key, (label, _) in SORTS.items()]

    @property
    def shown_label(self) -> str:
        return f"{len(self.groups)} of {self.matched}"


def _query_url(**params) -> str:
    from urllib.parse import urlencode

    # The tab is kept even when it is the default: with nothing needing
    # attention the page falls back to All, and a link to the default tab has
    # to be able to say it means the default.
    defaults = {"sort": DEFAULT_SORT, "page": 1}
    kept = {key: value for key, value in params.items() if value and value != defaults.get(key)}
    return f"?{urlencode(kept)}" if kept else "?"


def _matches(group: WorkGroup, search: str, language: str) -> tuple[bool, bool]:
    """Whether a work passes the search and language filter, and whether only an edition did."""

    through_edition = False
    if search:
        needle = search.casefold()
        if needle not in group.title.casefold() and needle not in group.author.casefold():
            if not any(needle in (row.edition.title or "").casefold() for row in group.rows):
                return False, False
            through_edition = True
    if language:
        languages = [row.edition.language for row in group.rows]
        if language not in languages:
            return False, False
        # A work found through its canonical original is found through itself.
        if not any(row.is_canonical and row.edition.language == language for row in group.rows):
            through_edition = True
    return True, through_edition


def catalogue_page(params, groups: list[WorkGroup]) -> CataloguePage:
    """Filter, sort and page the work groups by the request's query parameters.

    The tab picks which works need looking at; a search ignores the tab, since
    someone typing a title wants that book wherever it sits. With no tab asked
    for and nothing needing attention, the list opens on every work instead of
    on an empty page.
    """

    from almonium_book_processor.catalog.promotion import promotion_targets

    targets = [target.name for target in promotion_targets()]
    search = (params.get("q") or "").strip()
    language = (params.get("lang") or "").strip().lower()
    sort = params.get("sort") if params.get("sort") in SORTS else DEFAULT_SORT
    try:
        page = max(1, int(params.get("page") or 1))
    except ValueError:
        page = 1

    tests = {
        "attention": ("Needs attention", "work", lambda group: group.needs_attention),
        "processing": ("Processing", "work", lambda group: group.processing),
        **{
            f"behind-{target}": (
                f"Behind {target}",
                "edition",
                lambda group, target=target: group.behind_count(target) > 0,
            )
            for target in targets
        },
        "all": ("All", "work", lambda group: True),
    }
    tab = params.get("tab")
    if tab not in tests:
        tab = DEFAULT_TAB
        if not params.get("tab") and not any(group.needs_attention for group in groups):
            tab = "all"

    tabs = []
    for key, (label, unit, test) in tests.items():
        if key.startswith("behind-"):
            count = sum(group.behind_count(key.removeprefix("behind-")) for group in groups)
        else:
            count = sum(1 for group in groups if test(group))
        url = _query_url(tab=key, sort=sort, lang=language)
        tabs.append(CatalogueTab(key, label, count, unit, url, active=key == tab and not search))

    matched: list[WorkGroup] = []
    for group in groups:
        found, through_edition = _matches(group, search, language)
        if not found or (not search and not tests[tab][2](group)):
            continue
        group.matched_through_edition = through_edition
        matched.append(group)
    matched.sort(key=_sort_key(sort))

    rows = [row for group in matched for row in group.rows]
    if search:
        verb = "matches" if len(matched) == 1 else "match"
        breakdown = f"{_plural(len(matched), 'work')} {verb} \u201c{search}\u201d"
    elif tab == "attention":
        failed = sum(1 for row in rows if row.is_failed)
        review = sum(1 for row in rows if row.needs_review)
        parts = [f"{failed} failed"] if failed else []
        if review:
            parts.append(f"{review} {'needs' if review == 1 else 'need'} review")
        breakdown = " · ".join(parts) or "Nothing needs attention"
    elif tab == "processing":
        busy = sum(1 for row in rows if row.run or row.status in IN_FLIGHT_STATUSES)
        breakdown = f"{_plural(busy, 'edition')} processing"
    elif tab.startswith("behind-"):
        target = tab.removeprefix("behind-")
        behind = sum(group.behind_count(target) for group in matched)
        breakdown = f"{_plural(behind, 'edition')} behind {target}"
    else:
        breakdown = catalogue_summary(matched).label
    breakdown = f"{breakdown} · {SORTS[sort][1]}"

    shown = matched[: PAGE_SIZE * page]
    more_count = min(PAGE_SIZE, len(matched) - len(shown))
    more_url = ""
    if more_count:
        more_url = (
            _query_url(
                tab=tab if params.get("tab") else "",
                sort=sort,
                lang=language,
                q=search,
                page=page + 1,
            )
            + f"#work-{matched[len(shown)].work.id}"
        )

    languages = sorted(
        {row.edition.language for group in groups for row in group.rows},
        key=lambda code: language_name(code),
    )
    return CataloguePage(
        tab=tab,
        sort=sort,
        language=language,
        search=search,
        page=page,
        tabs=tabs,
        groups=shown,
        matched=len(matched),
        breakdown=breakdown,
        summary=catalogue_summary(groups),
        languages=[(code, language_name(code)) for code in languages],
        more_url=more_url,
        more_count=more_count,
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
