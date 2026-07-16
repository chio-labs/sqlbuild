"""Column declaration normalization for dataset-like Python nodes."""

from collections.abc import Sequence

from sqlbuild.python_nodes.types import LoaderColumnSpec, PythonNodeColumnSpec
from sqlbuild.spec.contracts.models import SourceColumnEntry


def normalize_columns(
    columns: Sequence[LoaderColumnSpec | PythonNodeColumnSpec | SourceColumnEntry],
) -> tuple[SourceColumnEntry, ...]:
    normalized: list[SourceColumnEntry] = []
    column: LoaderColumnSpec | PythonNodeColumnSpec | SourceColumnEntry
    for column in columns:
        if isinstance(column, SourceColumnEntry):
            normalized.append(column)
            continue
        column_type: object = column.get("type")
        nullable: object = column.get("nullable")
        description: object = column.get("description")
        meta: object = column.get("meta", {})
        normalized.append(
            SourceColumnEntry(
                name=str(column["name"]),
                type=str(column_type) if column_type is not None else None,
                nullable=bool(nullable) if nullable is not None else None,
                description=str(description) if description is not None else None,
                meta=meta if isinstance(meta, dict) else {},
            )
        )
    return tuple(normalized)
