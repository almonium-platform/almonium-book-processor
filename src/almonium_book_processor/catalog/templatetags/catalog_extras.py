from __future__ import annotations

import re

from django import template
from django.urls import reverse
from django.utils.html import format_html

register = template.Library()


@register.filter
def thousands(value):
    """A count with its thousands spaced, as the catalogue prints word counts."""

    try:
        return f"{int(value):,}".replace(",", "\u202f")
    except (TypeError, ValueError):
        return value


@register.filter
def mark_excerpt(text, quote):
    """The sentence around ``quote`` with the quote itself marked, escaped for HTML."""

    from django.utils.html import escape
    from django.utils.safestring import mark_safe

    from almonium_book_processor.catalog.fidelity_audit import excerpt

    before, span, after = excerpt(text or "", quote or "")
    if not span:
        return escape(before)
    return mark_safe(f"{escape(before)}<mark>{escape(span)}</mark>{escape(after)}")


@register.simple_tag
def side_excerpt(text, quote, counterpart=""):
    """The sentences of one side that hold the quoted words, this side's quote marked."""

    from django.utils.html import escape
    from django.utils.safestring import mark_safe

    from almonium_book_processor.catalog.fidelity_audit import side_excerpt as excerpt_side

    return mark_safe(
        "".join(
            f"<mark>{escape(s['text'])}</mark>" if s["marked"] else escape(s["text"])
            for s in excerpt_side(text or "", quote or "", counterpart or "")
        )
    )


@register.simple_tag
def change_preview(text, quote, suggestion):
    """The sentence after the suggestion, with removed words struck and new words marked."""

    from django.utils.html import escape
    from django.utils.safestring import mark_safe

    from almonium_book_processor.catalog.fidelity_audit import change_preview as preview

    segments, _placed = preview(text or "", quote or "", suggestion or "")
    html = []
    for segment in segments:
        if segment["op"] == "delete":
            html.append(f"<del>{escape(segment['text'])}</del>")
        elif segment["op"] == "insert":
            html.append(f"<ins>{escape(segment['text'])}</ins>")
        else:
            html.append(escape(segment["text"]))
    return mark_safe("".join(html))


@register.filter
def get_item(mapping, key):
    """Look a key up in a dict-like value; templates cannot index by variable."""

    if not hasattr(mapping, "get"):
        return None
    return mapping.get(key)


def _live(url: str, fingerprint: str) -> str:
    return format_html('data-live="{}" data-live-fingerprint="{}"', url, fingerprint)


@register.simple_tag
def live_work(edition):
    """Attributes that make an element follow every job of the edition's work.

    Put them on the element whose contents jobs change; live.js polls the
    activity endpoint and swaps that element in place when the work moves.
    """

    from almonium_book_processor.catalog.activity import work_activity

    return _live(
        reverse("catalog:edition-activity", args=[edition.id]),
        work_activity(edition.work)["fingerprint"],
    )


@register.simple_tag
def live_catalogue(visibility):
    """Attributes that make a catalogue list follow the jobs of its visibility."""

    from almonium_book_processor.catalog.activity import catalogue_activity

    url = reverse("catalog:catalogue-activity")
    return _live(f"{url}?visibility={visibility}", catalogue_activity(visibility)["fingerprint"])


@register.simple_tag
def live_removed():
    """Attributes that make the removal record follow withdrawals and purges."""

    from almonium_book_processor.catalog.activity import removed_activity

    return _live(reverse("catalog:removed-activity"), removed_activity()["fingerprint"])


@register.simple_tag
def cost(estimate):
    """The price suffix on a paid button: "· ~$0.14", or "· AI" when none is known."""

    if estimate is None:
        return ""
    return format_html(
        '<span class="cost"><span class="cost-sep" aria-hidden="true">·</span>'
        '<span class="cost-value">{}</span></span>',
        estimate.label,
    )


@register.simple_tag
def cost_attrs(estimate, choices=None, fields=""):
    """The button's tooltip and, above the threshold, its confirmation question.

    ``choices`` maps "value|value" of the ``fields`` (space-separated ids) to an
    estimate each, for a price that follows a select in the same form.
    """

    import json

    from django.utils.safestring import mark_safe

    if estimate is None:
        return ""
    attrs = format_html(' title="{}"', estimate.note)
    if estimate.confirm:
        attrs += format_html(' data-confirm="{}"', estimate.confirm)
    if choices:
        data = {
            key: {"label": item.label, "note": item.note, "confirm": item.confirm}
            for key, item in choices.items()
        }
        attrs += format_html(
            ' data-cost-from="{}" data-costs="{}"', fields, json.dumps(data, ensure_ascii=False)
        )
    return mark_safe(attrs)


@register.filter
def at(mapping, key):
    """``mapping[key]`` for a key the template holds in a variable."""

    try:
        return mapping[key]
    except (KeyError, TypeError, IndexError):
        return None


@register.filter
def usd(value):
    """Dollars as the AI spend panel prints them."""

    from almonium_book_processor.catalog.spend import format_usd

    return format_usd(value)


_ROMAN = re.compile(r"^[IVXLCDM]+$")


@register.filter
def display_title(value):
    """A source title shouted in capitals, title-cased for display; Roman numerals stay."""

    text = (value or "").strip().rstrip(".")
    letters = [ch for ch in text if ch.isalpha()]
    if not letters or not all(ch.isupper() for ch in letters):
        return text
    return " ".join(
        word if _ROMAN.match(word.rstrip(",;:")) else word.capitalize() for word in text.split()
    )


@register.filter
def short_hash(value):
    """A long hash or UUID as its first and last eight characters."""

    text = str(value or "").replace("-", "")
    return f"{text[:8]}…{text[-8:]}" if len(text) > 20 else str(value or "")
