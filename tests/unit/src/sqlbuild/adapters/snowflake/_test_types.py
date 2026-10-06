from dataclasses import dataclass
from datetime import datetime

from sqlbuild.adapter.contract.models import FunctionInfo, SchemaDiffResult
from sqlbuild.adapter.contract.types import TableFreshnessStatus
from sqlbuild.adapters.snowflake.classes.snowflake_adapter import SnowflakeAdapter
from sqlbuild.compiler.lineage.types import InferredNullability
from sqlbuild.cost.types import CostStatus


@dataclass(frozen=True)
class SnowflakeRetentionTestCase:
    description: str
    desired_days: int
    observed_row: tuple[object, ...]
    expected_days: int
    expected_kind: str
    expected_sql: str


@dataclass(frozen=True)
class SnowflakeTableTypeDdlTestCase:
    description: str
    table_type: str
    expected_prefix: str


@dataclass(frozen=True)
class SnowflakeCostCollectionTestCase:
    description: str
    connect_error: bool
    collection_error: bool
    close_error: bool
    expected_status: CostStatus
    expected_message_fragment: str | None = None
    expected_limitation_fragment: str | None = None


@dataclass(frozen=True)
class SnowflakeMergeExclusionTestCase:
    description: str
    expected_update_assignment: str
    expected_insert_clause: str


@dataclass(frozen=True)
class SnowflakeExpressionInferenceProfileTestCase:
    description: str
    expected_sql_analysis_dialect: str
    expected_identifier_limit: int
    expected_rule_results: dict[str, InferredNullability]
    expected_return_types: dict[str, str]


@dataclass(frozen=True)
class SnowflakeRenderCursorBoundLiteralTestCase:
    description: str
    value: str
    cursor_type: str | None
    expected_literal: str


@dataclass(frozen=True)
class SnowflakeRenderCloneTestCase:
    description: str
    source: str
    target: str
    hard_copy: bool
    origin_is_transient: bool
    expected_statements: tuple[str, ...]
    expected_supports_zero_copy: bool


@dataclass(frozen=True)
class SnowflakeMoveOrCopyRelationTestCase:
    description: str
    source: str
    target: str
    expected_statements: tuple[str, ...]


@dataclass(frozen=True)
class SnowflakeRenderIdentifierTestCase:
    description: str
    name: str
    expected_identifier: str


@dataclass(frozen=True)
class SnowflakeSchemaDiffTestCase:
    description: str
    expected_result: SchemaDiffResult


@dataclass(frozen=True)
class SnowflakeRenderPythonFunctionTestCase:
    description: str
    expected_sql: str


@dataclass(frozen=True)
class SnowflakeRenderTableFunctionTestCase:
    description: str
    expected_sql: str


@dataclass(frozen=True)
class SnowflakeQueryColumnNamesTestCase:
    description: str
    cursor_description: tuple[tuple[str], ...]
    expected_columns: tuple[str, ...]


@dataclass(frozen=True)
class SnowflakeLoadSeedTestCase:
    description: str
    csv_text: str
    expected_rows: list[tuple[object, ...]]


@dataclass(frozen=True)
class SnowflakeTableFreshnessMetadataTestCase:
    description: str
    row: tuple[object, ...]
    expected_data_version: datetime
    expected_value_kind: str
    expected_supports_metadata: bool


@dataclass(frozen=True)
class SnowflakeTableFreshnessBatchTestCase:
    description: str
    expected_data_versions: tuple[datetime, ...]
    expected_query_fragments: tuple[str, ...]


@dataclass(frozen=True)
class SnowflakeTableFreshnessOutcomeTestCase:
    description: str
    rows: tuple[tuple[object, ...], ...]
    expected_statuses: dict[str, TableFreshnessStatus]
    expected_message_fragments: dict[str, str]


@dataclass(frozen=True)
class SnowflakeTableFreshnessMetadataErrorTestCase:
    description: str
    row: tuple[object, ...] | None
    expected_error_fragment: str


@dataclass(frozen=True)
class SnowflakePruneSqlTestCase:
    description: str
    database: str | None
    schema: str
    retain_versions: int
    expected_fragments: tuple[str, ...]


@dataclass(frozen=True)
class SnowflakeConnectConfigTestCase:
    description: str
    config: dict[str, object]
    expected_connect_kwargs: dict[str, object]
    expected_session_statements: tuple[str, ...] = ()


@dataclass(frozen=True)
class SnowflakeInvalidSecondaryRolesTestCase:
    description: str
    secondary_roles: str
    expected_error: str


@dataclass(frozen=True)
class SnowflakeInformationSchemaFilterTestCase:
    description: str
    database: str
    schemas: tuple[str, ...]
    names: tuple[str, ...]
    expected_params: tuple[str, ...]


@dataclass(frozen=True)
class SnowflakeQualifiedColumnInspectionTestCase:
    description: str
    relation_count: int
    expected_statement_count: int


@dataclass(frozen=True)
class SnowflakeBatchedRetentionTestCase:
    description: str
    requests: tuple[tuple[str, str], ...]
    schema_rows: tuple[list[tuple[object, ...]], ...]
    expected_query_schemas: tuple[str, ...]
    expected_days: dict[str, int]


@dataclass(frozen=True)
class SnowflakeBatchedRetentionErrorTestCase:
    description: str
    requests: tuple[tuple[str, str], ...]
    rows: list[tuple[object, ...]]
    expected_error: str


@dataclass(frozen=True)
class SnowflakeRelationAgeMetadataTestCase:
    description: str
    relation_type: str
    created: datetime | None
    last_altered: datetime | None
    expected_created_at: datetime | None
    expected_last_altered_at: datetime | None


@dataclass(frozen=True)
class SnowflakeFunctionDiscoveryTestCase:
    description: str
    database: str | None
    schemas: tuple[str, ...] | None
    names: tuple[str, ...] | None
    rows: tuple[tuple[object, ...], ...]
    expected_relation: str
    expected_params: tuple[str, ...]
    expected_functions: tuple[FunctionInfo, ...]


@dataclass(frozen=True)
class SnowflakeStateTableDdlTestCase:
    description: str
    render_method: str
    expected_prefix: str
    expected_suffix: str


@dataclass(frozen=True)
class SnowflakeStateTableExactDdlTestCase:
    description: str
    render_method: str
    expected_sql: str


@dataclass(frozen=True)
class SnowflakeStateTableFallbackTestCase:
    description: str
    adapter_type: type[SnowflakeAdapter]
    rejection_errno: int
    rejection_message: str
    expected_executed_tables: tuple[str, ...]
    expected_executed_retention_days: tuple[str, ...]


@dataclass(frozen=True)
class SnowflakeStateTableRetentionErrorTestCase:
    description: str
    errno: int
    message: str
    expected_executed_count: int
    expected_next_retention_days: str


@dataclass(frozen=True)
class SnowflakeNonStateRetentionErrorTestCase:
    description: str
    sql: str
    expected_executed_sql: tuple[str, ...]


@dataclass(frozen=True)
class SnowflakeStateTableFallbackLifecycleTestCase:
    description: str
    rejections: tuple[tuple[tuple[str, ...], Exception], ...]
    expected_statement_events: tuple[str, ...]
    expected_progress_fail_lines: int
    expected_executed_retention_days: tuple[str, ...]


@dataclass(frozen=True)
class SnowflakeStateTableSchemaFallbackTestCase:
    description: str
    rejecting_schema: str
    accepting_schema: str
    expected_executed: tuple[tuple[str, str], ...]
