from dataclasses import dataclass, field

from sqlbuild.adapter.shared.models import (
    ColumnInfo,
    QueryResult,
    RowDiffResult,
    RowDiffSampleRow,
    SchemaDiffResult,
)


@dataclass(frozen=True)
class DatabricksQueryTestCase:
    description: str
    sql: str
    limit: int | None
    expected_result: QueryResult


@dataclass(frozen=True)
class DatabricksSchemaIntrospectionTestCase:
    description: str
    setup_sql: tuple[str, ...]
    expected_relation_exists: bool
    expected_schema_exists: bool
    expected_relation_names: tuple[str, ...]
    expected_columns: tuple[ColumnInfo, ...]
    expected_all_columns: dict[str, tuple[ColumnInfo, ...]]
    expected_query_column_names: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class DatabricksSchemaDiffTestCase:
    description: str
    left_sql: str
    right_sql: str
    expected_result: SchemaDiffResult


@dataclass(frozen=True)
class DatabricksRowDiffTestCase:
    description: str
    left_sql: str
    right_sql: str
    unique_key: str | tuple[str, ...]
    expected_result: RowDiffResult


@dataclass(frozen=True)
class DatabricksRowDiffSampleTestCase:
    description: str
    left_sql: str
    right_sql: str
    unique_key: str | tuple[str, ...]
    side: str
    expected_unequal_samples: tuple[RowDiffSampleRow, ...] = field(default_factory=tuple)
    expected_side_only_samples: tuple[tuple[tuple[str, object], ...], ...] = field(
        default_factory=tuple
    )


@dataclass(frozen=True)
class DatabricksBuildFlowTestCase:
    description: str
    seed_csv: str
    expected_rows: tuple[tuple[object, ...], ...]
    expected_statement_count: int = 0


@dataclass(frozen=True)
class DatabricksMergeTestCase:
    description: str
    target_setup_sql: tuple[str, ...]
    source_sql: str
    unique_key: str | tuple[str, ...]
    expected_rows: tuple[tuple[object, ...], ...]


@dataclass(frozen=True)
class DatabricksFingerprintTestCase:
    description: str
    query_sql: str
    expected_model_name: str
    expected_target_name: str
