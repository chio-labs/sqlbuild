from __future__ import annotations

from dataclasses import dataclass

from sqlbuild._native import ColumnTransformKind


@dataclass(frozen=True)
class ColumnLineageAnalyzerTestCase:
    description: str
    model_name: str
    query_sql: str
    inferred_columns: tuple[str, ...] | None
    upstream_model_columns: dict[str, tuple[str, ...]]
    upstream_seed_columns: dict[str, tuple[str, ...]]
    expected_column: str
    expected_upstream_columns: tuple[str, ...]
    expected_transform_kind: ColumnTransformKind


@dataclass(frozen=True)
class ProjectLineageGraphTestCase:
    description: str
    expected_consumers: tuple[str, ...]


@dataclass(frozen=True)
class SqlAnalysisDisabledLineageTestCase:
    description: str
    sql_analysis_enabled: bool
    expected_result_is_none: bool


@dataclass(frozen=True)
class RichLineageAnalysisScalingTestCase:
    description: str
    chain_length: int
    unrelated_model_counts: tuple[int, ...]
    expected_model_names: tuple[str, ...]


@dataclass(frozen=True)
class ExpectedCountTestCase:
    description: str
    expected_count: int


@dataclass(frozen=True)
class PythonRecordFallbackTestCase:
    description: str
    expected_upstream_resource: str
    expected_fallbacks_counted: bool
