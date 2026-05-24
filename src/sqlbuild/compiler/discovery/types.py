"""Discovery domain types."""

from __future__ import annotations

from enum import StrEnum


class LoaderConnectionMode(StrEnum):
    """How a source loader owns the destination warehouse connection."""

    SQLBUILD = "sqlbuild"
    EXTERNAL = "external"
