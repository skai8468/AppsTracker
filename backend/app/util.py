"""Small shared helpers with no dependencies on the rest of the app."""
from __future__ import annotations


def slugify(name: str) -> str:
    """Lowercase, non-alphanumerics -> hyphens, trimmed and capped. Used to derive a
    stable Company.slug from a display name."""
    return "".join(c if c.isalnum() else "-" for c in name.lower()).strip("-")[:80]
