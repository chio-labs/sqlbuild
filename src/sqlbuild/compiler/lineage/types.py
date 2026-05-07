"""Column lineage domain types."""

from __future__ import annotations

from enum import StrEnum


class ColumnTransformKind(StrEnum):
    """High-level transform classification for one output column."""

    DIRECT = "direct"
    CAST = "cast"
    EXPRESSION = "expression"
    AGGREGATION = "aggregation"
    STAR = "star"
    CONSTANT = "constant"
    UNKNOWN = "unknown"


class InferredNullability(StrEnum):
    """Conservative nullability state inferred for an output column."""

    NON_NULL = "non_null"
    NULLABLE = "nullable"
    UNKNOWN = "unknown"


class ColumnLineageConfidence(StrEnum):
    """Coarse confidence that a lineage edge is fully understood."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    UNKNOWN = "unknown"


class ColumnLineageMode(StrEnum):
    """Column lineage analyzer mode."""

    RICH = "rich"
    FAST = "fast"
