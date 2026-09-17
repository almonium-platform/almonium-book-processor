from __future__ import annotations

from django import template

from almonium_book_processor.catalog.catalogue import display_title as _display_title

register = template.Library()


@register.filter
def display_title(title):
    """A source title as the reader should see it: an all-capitals one calmed down."""

    return _display_title(title or "")


@register.filter
def get_item(mapping, key):
    """Look a key up in a dict-like value; templates cannot index by variable."""

    if not hasattr(mapping, "get"):
        return None
    return mapping.get(key)
