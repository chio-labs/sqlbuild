"""Column-lineage declaration normalization for Python assets."""

from collections.abc import Mapping, Sequence

from sqlbuild.python_nodes.models import ColumnLineageRef
from sqlbuild.python_nodes.types import ColumnLineageRefSpec


def normalize_column_lineage(
    value: Mapping[str, Sequence[ColumnLineageRefSpec | ColumnLineageRef]] | None,
) -> dict[str, tuple[ColumnLineageRef, ...]] | None:
    if value is None:
        return None
    normalized: dict[str, tuple[ColumnLineageRef, ...]] = {}
    for column_name, refs in value.items():
        normalized[str(column_name)] = tuple(normalize_column_lineage_ref(ref) for ref in refs)
    return normalized


def normalize_column_lineage_ref(
    value: ColumnLineageRefSpec | ColumnLineageRef,
) -> ColumnLineageRef:
    if isinstance(value, ColumnLineageRef):
        return value
    return ColumnLineageRef(node=str(value["node"]), column=str(value["column"]))
