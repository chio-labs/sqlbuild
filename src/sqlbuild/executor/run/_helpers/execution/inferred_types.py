"""Compiled column types handed to adapters whose CTAS cannot keep expression types."""

from __future__ import annotations

from sqlbuild._native import ModelPlanEntry


def inferred_column_types(entry: ModelPlanEntry) -> dict[str, str]:
    """Return the model's inferred output column types by name."""

    return {column.name: column.type for column in entry.inferred_columns}
