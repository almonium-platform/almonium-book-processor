"""What the edition page's rail says, and how its review items are grouped.

The rail answers one question before anything else: what does this edition
need from a person right now. ``next_step`` computes that sentence and the one
action that goes with it, so the page never shows an "Editor decision" panel,
a "Ready to publish" panel and a promotion form that all say the same thing
in different words.

Review items are grouped by code. Sixty-five ``alignment_low_confidence``
warnings are one problem with sixty-five instances, not sixty-five problems,
so the page shows one bar per code with its count, confidence range and
chapter range, and the rows under it sorted by what is worst.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from django.urls import reverse

from almonium_book_processor.catalog.catalogue import ROLE_ORDER, SHORT_ROLE_LABELS
from almonium_book_processor.catalog.models import Edition

# The last percentage in a warning message is the confidence it reports.
_PERCENT = re.compile(r"(\d+(?:\.\d+)?)\s?%")

# Below these a confidence reads as red, then amber, in the review rows.
CONFIDENCE_LOW = 60.0
CONFIDENCE_MID = 75.0

# Rows shown per group before "Show N more".
GROUP_PREVIEW = 5

# What a code's items are about, in the words a reviewer uses. A code without an
# entry falls back to its identifier.
CODE_LABELS = {
    "alignment_low_confidence": "Alignment group needs a look",
    "alignment_coverage_gap": "Untranslated passage",
    "adaptation_fidelity_review": "Fidelity review",
    "adaptation_chapter_replaced": "Chapter replaced by a pilot",
    "adaptation_difficulty_gate": "Difficulty gate",
    "translation_title_page": "Title page not translated",
}


@dataclass
class ReviewRow:
    item: dict
    confidence: float | None
    chapter: int | None
    position: int

    @property
    def warning(self):
        return self.item["warning"]

    @property
    def block_label(self) -> str:
        block = self.warning.block
        return block.block_id if block is not None else ""

    @property
    def text(self) -> str:
        """One line for the row: the code's label when it has one, else the message.

        A labelled code's message is formulaic and repeats the confidence
        column; the full message stays in the row's title.
        """

        return CODE_LABELS.get(self.warning.code) or self.warning.message

    @property
    def confidence_label(self) -> str:
        return f"{self.confidence:.1f}%" if self.confidence is not None else ""

    @property
    def confidence_class(self) -> str:
        if self.confidence is None:
            return ""
        if self.confidence < CONFIDENCE_LOW:
            return "confidence-low"
        if self.confidence < CONFIDENCE_MID:
            return "confidence-mid"
        return ""


@dataclass
class ReviewGroup:
    code: str
    rows: list[ReviewRow] = field(default_factory=list)

    @property
    def label(self) -> str:
        return CODE_LABELS.get(self.code, self.code.replace("_", " "))

    @property
    def count(self) -> int:
        return len(self.rows)

    @property
    def has_confidence(self) -> bool:
        return any(row.confidence is not None for row in self.rows)

    @property
    def hidden(self) -> int:
        return max(0, len(self.rows) - GROUP_PREVIEW)

    @property
    def range_label(self) -> str:
        """``65 · 53.7–72.0% · ch. 20–30``, dropping what the group does not have."""

        parts = [str(self.count)]
        confidences = [row.confidence for row in self.rows if row.confidence is not None]
        if confidences:
            low, high = min(confidences), max(confidences)
            parts.append(f"{low:.1f}%" if low == high else f"{low:.1f}–{high:.1f}%")
        chapters = [row.chapter for row in self.rows if row.chapter is not None]
        if chapters:
            low, high = min(chapters), max(chapters)
            parts.append(f"ch. {low}" if low == high else f"ch. {low}–{high}")
        return " · ".join(parts)


def _confidence(message: str) -> float | None:
    matches = _PERCENT.findall(message or "")
    return float(matches[-1]) if matches else None


def review_groups(items: list[dict]) -> list[ReviewGroup]:
    """Open review items grouped by code, the largest group first, worst rows first."""

    groups: dict[str, ReviewGroup] = {}
    for position, item in enumerate(items):
        warning = item["warning"]
        block = warning.block
        chapter = block.chapter.sequence if block is not None and block.chapter_id else None
        row = ReviewRow(
            item=item,
            confidence=_confidence(warning.message),
            chapter=chapter,
            position=position,
        )
        groups.setdefault(warning.code, ReviewGroup(code=warning.code)).rows.append(row)
    for group in groups.values():
        if group.has_confidence:
            group.rows.sort(
                key=lambda row: (row.confidence is None, row.confidence or 0.0, row.position)
            )
        else:
            group.rows.sort(key=lambda row: (row.chapter is None, row.chapter or 0, row.position))
    return sorted(groups.values(), key=lambda group: (-group.count, group.code))


def work_tree(edition: Edition) -> list[dict[str, Any]]:
    """Every edition of the work as the rail lists it: canonical, parallels, standalones."""

    rows = []
    for item in Edition.objects.filter(work=edition.work).order_by("language"):
        rows.append(
            {
                "edition": item,
                "language": item.language.upper(),
                "role_label": SHORT_ROLE_LABELS[item.parallel_role],
                "current": item.id == edition.id,
                "url": reverse("catalog:edition-detail", args=[item.id]),
            }
        )
    rows.sort(key=lambda row: (ROLE_ORDER.index(row["edition"].parallel_role), row["language"]))
    return rows


def next_step(edition: Edition, context: dict[str, Any]) -> dict[str, Any]:
    """The one thing this edition is waiting for, and the control that does it.

    ``kind`` names the control the template draws: a form for a decision the
    page can take, a link to the panel that holds a longer one, or nothing
    when the edition is waiting on a worker or on no one.
    """

    is_private = context["is_private"]
    active = context["active_runs"]
    if active:
        run = active[0]
        return {
            "kind": "running",
            "run": run,
            "text": f"{run.get_stage_display()} is running; this page follows it.",
        }
    if edition.status == Edition.Status.FAILED:
        return {
            "kind": "retry",
            "text": (
                "Processing failed. Retry after correcting the worker, importer or source problem."
            ),
        }
    if edition.status in (Edition.Status.QUEUED, Edition.Status.PROCESSING, Edition.Status.DRAFT):
        return {"kind": "wait", "text": "Waiting for processing to finish."}
    open_items = context["actionable_warnings"]
    if edition.status == Edition.Status.REVIEW:
        if open_items:
            count = len(open_items)
            noun = "review item" if count == 1 else "review items"
            if is_private:
                return {
                    "kind": "repair",
                    "text": (
                        f"Resolve the {count} remaining {noun}, or repair the text and "
                        "release it to the owner."
                    ),
                }
            return {
                "kind": "resolve",
                "text": f"Resolve the {count} remaining {noun}, then approve.",
            }
        if is_private:
            return {
                "kind": "repair",
                "text": "Repair the text if it needs it, then make it available to the owner.",
            }
        if blocker := context.get("adaptation_blocker"):
            return {
                "kind": "gate",
                "text": "All review items are resolved, but the difficulty gate is not passing. "
                + blocker
                + (
                    " The text changed after the last analysis: analyse again, then come back."
                    if context.get("projection_state") == "stale"
                    else ""
                ),
            }
        text = "All review items are resolved. Completing review marks this edition ready"
        if context.get("adaptation_target") and not edition.cefr_level:
            text += f" and labels it {context['adaptation_target']}, the level it was generated for"
        return {"kind": "approve", "text": text + "; it does not publish it."}
    if is_private:
        return {
            "kind": "available",
            "text": "Available in the owner's private reader. Nothing to do.",
        }
    if edition.status == Edition.Status.READY:
        if blocked := context.get("publish_blocked"):
            return {"kind": "publish", "blocked": blocked, "text": blocked}
        return {
            "kind": "publish",
            "text": (
                "Reviewed and ready. Publishing sends it to Almonium; it is visible there once "
                "the hand-off succeeds."
            ),
        }
    if edition.status == Edition.Status.PUBLISHED:
        if context.get("publication_stale"):
            return {
                "kind": "update",
                "text": (
                    "Almonium still shows the metadata this edition was published with. Update it."
                ),
            }
        rows = [row for row in context["release_rows"] if row["target"] != "here"]
        behind = next((row for row in rows if row["state"] == "behind"), None)
        if behind is not None:
            return {
                "kind": "promote",
                "target": behind["target"],
                "text": f"Promote to {behind['target']}: {behind['corrections']} correction"
                f"{'' if behind['corrections'] == 1 else 's'} and {behind['artifacts']} new "
                f"artifact{'' if behind['artifacts'] == 1 else 's'} since the last promotion.",
            }
        never = next((row for row in rows if row["state"] == "never"), None)
        if never is not None:
            return {
                "kind": "promote",
                "target": never["target"],
                "text": f"Promote to {never['target']}. It has never had this edition.",
            }
        if any(row["state"] == "running" for row in rows):
            return {"kind": "wait", "text": "A promotion is running; this page follows it."}
        return {"kind": "done", "text": "Readers everywhere have the current edition."}
    return {"kind": "done", "text": "Nothing to do."}
