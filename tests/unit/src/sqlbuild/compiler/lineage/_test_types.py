from __future__ import annotations

from dataclasses import dataclass

from sqlbuild.compiler.lineage.types import ColumnTransformKind


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
    expected_internal_scope_names: tuple[str, ...] = ()


@dataclass(frozen=True)
class ProjectLineageGraphTestCase:
    description: str
    expected_trace: tuple[str, ...]
    expected_consumers: tuple[str, ...]
    expected_downstream_trace: tuple[str, ...]


@dataclass(frozen=True)
class SqlAnalysisDisabledLineageTestCase:
    description: str
    sql_analysis_enabled: bool
    expected_result_is_none: bool
