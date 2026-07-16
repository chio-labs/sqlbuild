from dataclasses import dataclass, field
from datetime import datetime

from sqlbuild.adapter.contract.models import (
    ColumnInfo,
    QueryResult,
    RowDiffResult,
    RowDiffSampleRow,
    SchemaDiffResult,
)
from sqlbuild.compiler.lineage.types import InferredNullability


@dataclass(frozen=True)
class SnowflakeExpressionNullabilityRuleTestCase:
    description: str
    function_name: str
    sql_expression: str
    rule_args: tuple[InferredNullability, ...]
    expected_nullability: InferredNullability
    expected_is_null: bool


@dataclass(frozen=True)
class SnowflakeQueryTestCase:
    description: str
    sql: str
    limit: int | None
    expected_result: QueryResult


@dataclass(frozen=True)
class SnowflakeSchemaIntrospectionTestCase:
    description: str
    setup_sql: tuple[str, ...]
    expected_relation_exists: bool
    expected_schema_exists: bool
    expected_relation_names: tuple[str, ...]
    expected_columns: tuple[ColumnInfo, ...]
    expected_all_columns: dict[str, tuple[ColumnInfo, ...]]
    expected_query_column_names: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class SnowflakeSchemaDiffTestCase:
    description: str
    left_sql: str
    right_sql: str
    expected_result: SchemaDiffResult


@dataclass(frozen=True)
class SnowflakeRowDiffTestCase:
    description: str
    left_sql: str
    right_sql: str
    unique_key: str | tuple[str, ...]
    expected_result: RowDiffResult


@dataclass(frozen=True)
class SnowflakeRowDiffSampleTestCase:
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
class SnowflakeBuildFlowTestCase:
    description: str
    seed_csv: str
    expected_rows: tuple[tuple[object, ...], ...]
    expected_statement_count: int = 0


@dataclass(frozen=True)
class SnowflakeRelationReuseCopyTestCase:
    description: str
    hard_copy: bool
    destination_name: str
    expected_rows: tuple[tuple[object, ...], ...]
    expected_recorded_fragment: str


@dataclass(frozen=True)
class SnowflakeMergeTestCase:
    description: str
    target_setup_sql: tuple[str, ...]
    source_sql: str
    unique_key: str | tuple[str, ...]
    expected_rows: tuple[tuple[object, ...], ...]


@dataclass(frozen=True)
class SnowflakeTableFreshnessMetadataTestCase:
    description: str
    expected_value_kind: str
    expected_supports_metadata: bool
    expected_data_version_type: type[datetime]


@dataclass(frozen=True)
class SnowflakeE2ETestCase:
    description: str
    command: tuple[str, ...]
    expected_stdout_fragments: tuple[str, ...] = field(default_factory=tuple)
    expected_return_code: int = 0
