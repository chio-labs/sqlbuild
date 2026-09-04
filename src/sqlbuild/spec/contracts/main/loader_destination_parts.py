"""Loader destination parsing contract."""

from __future__ import annotations

from sqlbuild.spec.contracts.constants import (
    LOADER_QUALIFIED_TABLE_PART_COUNT,
    LOADER_SCHEMA_TABLE_PART_COUNT,
)
from sqlbuild.spec.contracts.exceptions import SpecConfigError
from sqlbuild.spec.contracts.models import LoaderDestinationParts


def loader_destination_parts(
    *, destination: str, default_database: str | None, default_schema: str | None
) -> LoaderDestinationParts:
    """Parse a one-, two-, or three-part loader destination."""

    parts: tuple[str, ...] = tuple(destination.split("."))
    if not 1 <= len(parts) <= LOADER_QUALIFIED_TABLE_PART_COUNT or any(
        not part.strip() for part in parts
    ):
        raise SpecConfigError(
            f"Invalid loader destination '{destination}': expected 1 to 3 non-empty "
            "dot-separated parts (table, schema.table, or database.schema.table)"
        )
    if len(parts) == 1:
        return LoaderDestinationParts(default_database, default_schema, parts[0])
    if len(parts) == LOADER_SCHEMA_TABLE_PART_COUNT:
        return LoaderDestinationParts(default_database, parts[0], parts[1])
    return LoaderDestinationParts(parts[0], parts[1], parts[2])
