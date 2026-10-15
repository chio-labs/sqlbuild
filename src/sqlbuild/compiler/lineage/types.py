"""Column lineage domain types."""

from __future__ import annotations

from enum import StrEnum


class InferredNullability(StrEnum):
    """Conservative nullability state inferred for an output column."""

    NON_NULL = "non_null"
    NULLABLE = "nullable"
    UNKNOWN = "unknown"
