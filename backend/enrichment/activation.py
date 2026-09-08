"""Fail-closed activation gates for the enrichment foundation."""

from __future__ import annotations

from typing import Any


FOUNDATION_PROJECTION_FLAG = "enrichment.foundation_projection_enabled"
FOUNDATION_PUBLICATION_FLAG = "enrichment.foundation_publication_enabled"


def foundation_projection_enabled(config_store: Any = None) -> bool:
    """Return false unless a caller explicitly supplies a config-store opt-in."""

    if config_store is None:
        return False
    return bool(config_store.get_value(FOUNDATION_PROJECTION_FLAG, False))


def foundation_publication_enabled(config_store: Any = None) -> bool:
    """Publication is hard-disabled in this foundation PR."""

    del config_store
    return False


__all__ = [
    "FOUNDATION_PROJECTION_FLAG",
    "FOUNDATION_PUBLICATION_FLAG",
    "foundation_projection_enabled",
    "foundation_publication_enabled",
]
