"""Public entry for serializing a column lineage edge to a stable JSON payload."""

from __future__ import annotations

from collections.abc import Callable

from sqlbuild.compiler.lineage.main.serialize_column import serialize_column
from sqlbuild.compiler.lineage.models import ColumnLineageEdge, QualifiedLineageColumn


def serialize_column_edge(
    *,
    edge: ColumnLineageEdge,
    render_resource_type: Callable[[QualifiedLineageColumn], str],
) -> dict[str, object]:
    """Serialize a column lineage edge using a caller-provided resource renderer."""

    return {
        "source": serialize_column(column=edge.source, render_resource_type=render_resource_type),
        "target": serialize_column(column=edge.target, render_resource_type=render_resource_type),
        "transform": str(edge.transform_kind),
        "confidence": str(edge.confidence),
    }
