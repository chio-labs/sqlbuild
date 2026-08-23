"""Model-schema column parsing entrypoint for compiler consumers."""

from __future__ import annotations

from pathlib import Path

from sqlbuild.compiler.compile.exceptions import CompileInputError
from sqlbuild.compiler.discovery._helpers.sql.schema_columns import (
    parse_schema_columns as _parse_schema_columns,
)
from sqlbuild.compiler.discovery.exceptions import DeclarationParseError
from sqlbuild.spec.contracts.models import SchemaColumn, SourceLocation


def parse_schema_columns(
    *,
    raw_columns: object | None,
    file_path: Path,
    label: str,
    error_class: type[CompileInputError] | type[DeclarationParseError],
    column_locations: dict[str, SourceLocation] | None = None,
    require_columns: bool = False,
) -> tuple[SchemaColumn, ...]:
    """Parse authored model columns through the discovery-owned implementation."""

    return _parse_schema_columns(
        raw_columns=raw_columns,
        file_path=file_path,
        label=label,
        error_class=error_class,
        column_locations=column_locations,
        require_columns=require_columns,
    )
