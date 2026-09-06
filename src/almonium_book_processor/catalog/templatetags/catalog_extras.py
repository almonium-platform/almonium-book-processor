from __future__ import annotations

from django import template

register = template.Library()


@register.filter
def get_item(mapping, key):
    """Look a key up in a dict-like value; templates cannot index by variable."""

    if not hasattr(mapping, "get"):
        return None
    return mapping.get(key)
