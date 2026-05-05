from dataclasses import dataclass

from sqlbuild.adapter.shared.models import (
    ColumnInfo,
    RowDiffResult,
    RowDiffSampleRow,
    SchemaDiffResult,
)


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
    left_relation_columns: tuple[ColumnInfo, ...] | None = None
    right_relation_columns: tuple[ColumnInfo, ...] | None = None


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
