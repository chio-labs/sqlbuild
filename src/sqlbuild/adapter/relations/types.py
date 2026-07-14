"""Adapter relation naming contracts."""

from typing import Protocol


class RelationLocation(Protocol):
    """Structural relation location accepted by adapter naming."""

    database: str | None
    schema: str | None
    name: str
    qualified_name: str | None
