from dataclasses import dataclass, field

from sqlbuild.adapter.shared.models import (
    ColumnInfo,
    QueryResult,
    RowDiffResult,
    RowDiffSampleRow,
    SchemaDiffResult,
)
from sqlbuild.compiler.lineage.types import InferredNullability


@dataclass(frozen=True)
class BigQueryExpressionNullabilityRuleTestCase:
    description: str
    function_name: str
    sql_expression: str
    rule_args: tuple[InferredNullability, ...]
    expected_nullability: InferredNullability
    expected_is_null: bool


@dataclass(frozen=True)
class BigQueryQueryTestCase:
    description: str
    sql: str
    limit: int | None
    expected_result: QueryResult


@dataclass(frozen=True)
class BigQuerySchemaIntrospectionTestCase:
    description: str
    setup_sql: tuple[str, ...]
    expected_relation_exists: bool
    expected_schema_exists: bool
    expected_relation_names: tuple[str, ...]
    expected_columns: tuple[ColumnInfo, ...]
    expected_all_columns: dict[str, tuple[ColumnInfo, ...]]
    expected_query_column_names: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class BigQuerySchemaDiffTestCase:
    description: str
    left_sql: str
    right_sql: str
    expected_result: SchemaDiffResult


@dataclass(frozen=True)
class BigQueryRowDiffTestCase:
    description: str
    left_sql: str
    right_sql: str
    unique_key: str | tuple[str, ...]
    expected_result: RowDiffResult


@dataclass(frozen=True)
class BigQueryRowDiffSampleTestCase:
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
class BigQueryBuildFlowTestCase:
    description: str
    seed_csv: str
    staging_sql: str
    expected_rows: tuple[tuple[object, ...], ...]
    expected_recorded_fragment: str
    expected_statement_count: int = 0


@dataclass(frozen=True)
class BigQueryMergeTestCase:
    description: str
    target_setup_sql: tuple[str, ...]
    source_sql: str
    unique_key: str | tuple[str, ...]
    expected_rows: tuple[tuple[object, ...], ...]


@dataclass(frozen=True)
class BigQueryDeleteInsertCursorTestCase:
    description: str
    target_setup_sql: tuple[str, ...]
    source_sql: str
    cursor_column: str
    cursor_start: str
    cursor_end: str
    columns: tuple[str, ...]
    expected_rows: tuple[tuple[object, ...], ...]
    expected_recorded_fragment: str


@dataclass(frozen=True)
class BigQueryFingerprintTestCase:
    description: str
    query_sql: str
    expected_model_name: str
    expected_target_name: str
