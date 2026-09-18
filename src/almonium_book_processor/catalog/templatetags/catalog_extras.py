from __future__ import annotations

from django import template

from almonium_book_processor.catalog.catalogue import display_title as _display_title

register = template.Library()


@register.filter
def display_title(title):
    """A source title as the reader should see it: an all-capitals one calmed down."""

    return _display_title(title or "")


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
