"""Physical columns of the relations a model reads, as inspected by the planner."""

from __future__ import annotations

from collections.abc import Mapping

from sqlbuild.adapter.contract.models import ColumnInfo
from sqlbuild.compiler.planner.constants import REF_INPUT_FUNCTION, SOURCE_INPUT_FUNCTION


class KnownInputColumns:
    """Look up the lower-cased physical columns a query binds against, or None when unknown."""

    def __init__(
        self,
        *,
        model_columns: Mapping[str, tuple[ColumnInfo, ...]],
        source_columns: Mapping[str, tuple[ColumnInfo, ...]],
    ) -> None:
        self._inspected: dict[str, Mapping[str, tuple[ColumnInfo, ...]]] = {
            REF_INPUT_FUNCTION: model_columns,
            SOURCE_INPUT_FUNCTION: source_columns,
        }

    def __call__(self, kind: str, name: str) -> frozenset[str] | None:
        """Return the inspected columns of one __source or __ref relation, or None."""

        columns: tuple[ColumnInfo, ...] = self._inspected.get(kind, {}).get(name, ())
        if not columns:
            return None
        return frozenset(column.name.lower() for column in columns)
