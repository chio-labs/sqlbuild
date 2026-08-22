from dataclasses import dataclass
from datetime import datetime

from sqlbuild.adapter.contract.models import (
    ColumnInfo,
    RowDiffResult,
    RowDiffSampleRow,
    SchemaDiffResult,
)
from sqlbuild.compiler.lineage.types import InferredNullability


@dataclass(frozen=True)
class BigQueryMergeExclusionTestCase:
    description: str
    expected_update_assignment: str
    expected_insert_clause: str


@dataclass(frozen=True)
class BigQueryExpressionInferenceProfileTestCase:
    description: str
    expected_sql_analysis_dialect: str
    expected_identifier_limit: int
    expected_rule_results: dict[str, InferredNullability]


@dataclass(frozen=True)
class BigQueryQueryTestCase:
    description: str
    sql: str
    limit: int | None
    expected_columns: tuple[str, ...]
    expected_rows: tuple[tuple[object, ...], ...]
    expected_truncated: bool


@dataclass(frozen=True)
class BigQueryRenderSchemaTestCase:
    description: str
    database: str | None
    schema: str
    location: str | None
    expected_sql: str


@dataclass(frozen=True)
class BigQueryRenderQualifiedNameTestCase:
    description: str
    database: str | None
    schema: str | None
    name: str
    expected_qualified_name: str | None


@dataclass(frozen=True)
class BigQueryRenderCloneTestCase:
    description: str
    source: str
    target: str
    hard_copy: bool
    expected_statements: tuple[str, ...]
    expected_supports_zero_copy: bool


@dataclass(frozen=True)
class BigQueryRenderDropViewTestCase:
    description: str
    target: str
    expected_statements: tuple[str, ...]


@dataclass(frozen=True)
class BigQueryRenderPythonFunctionTestCase:
    description: str
    expected_sql: str


@dataclass(frozen=True)
class BigQueryRenderTableFunctionTestCase:
    description: str
    expected_sql: str


@dataclass(frozen=True)
class BigQuerySchemaExistsTestCase:
    description: str
    missing_dataset: bool
    expected_exists: bool


@dataclass(frozen=True)
class BigQueryConnectErrorTestCase:
    description: str
    config: dict[str, object]
    expected_error_fragment: str


@dataclass(frozen=True)
class BigQueryExecutionErrorTestCase:
    description: str
    error_message: str
    error_details: list[dict[str, object]]
    expected_error_fragment: str
    expected_error_code: str


@dataclass(frozen=True)
class BigQueryRenderCursorBoundLiteralTestCase:
    description: str
    value: str
    cursor_type: str | None
    expected_literal: str


@dataclass(frozen=True)
class BigQueryRenderDeleteInsertTestCase:
    description: str
    expected_fragments: tuple[str, ...]
    unexpected_fragments: tuple[str, ...]


@dataclass(frozen=True)
class BigQuerySchemaDiffTestCase:
    description: str
    expected_result: SchemaDiffResult
    relation_columns: dict[str, tuple[ColumnInfo, ...]]


@dataclass(frozen=True)
class BigQueryRowDiffTestCase:
    description: str
    expected_result: RowDiffResult


@dataclass(frozen=True)
class BigQuerySampleRowsTestCase:
    description: str
    expected_unequal_samples: tuple[RowDiffSampleRow, ...]
    expected_side_only_samples: tuple[tuple[tuple[str, object], ...], ...]


@dataclass(frozen=True)
class BigQueryCountRowsTestCase:
    description: str
    expected_count: int
    expected_sql: str


@dataclass(frozen=True)
class BigQueryPruneSqlTestCase:
    description: str
    database: str | None
    schema: str
    retain_versions: int
    expected_fragments: tuple[str, ...]


@dataclass(frozen=True)
class BigQueryTableFreshnessBatchTestCase:
    description: str
    location: str
    expected_data_versions: tuple[datetime, ...]
    expected_query_fragments: tuple[str, ...]


@dataclass(frozen=True)
class BigQueryTableFreshnessWildcardTestCase:
    description: str
    table_name: str
    expected_error_fragment: str
