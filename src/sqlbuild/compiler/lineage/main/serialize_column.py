"""Public entry for serializing a qualified lineage column to a JSON payload."""

from __future__ import annotations

from collections.abc import Callable

from sqlbuild.compiler.lineage.models import QualifiedLineageColumn


def serialize_column(
    column: QualifiedLineageColumn,
    *,
    render_resource_type: Callable[[QualifiedLineageColumn], str],
) -> dict[str, object]:
    """Serialize a qualified lineage column using a caller-provided resource renderer."""

    return {
        "resource_type": render_resource_type(column),
        "resource_name": column.resource_name,
        "column_name": column.column_name,
    }
