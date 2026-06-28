from dataclasses import dataclass
from datetime import datetime

from sqlbuild.adapter.shared.models import SchemaDiffResult
from sqlbuild.compiler.lineage.types import InferredNullability


@dataclass(frozen=True)
class SnowflakeExpressionInferenceProfileTestCase:
    description: str
    expected_sql_analysis_dialect: str
    expected_identifier_limit: int
    expected_rule_results: dict[str, InferredNullability]


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


@dataclass(frozen=True)
class SnowflakeInformationSchemaFilterTestCase:
    description: str
    database: str
    schemas: tuple[str, ...]
    names: tuple[str, ...]
    expected_params: tuple[str, ...]
