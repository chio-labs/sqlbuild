from dataclasses import dataclass
from datetime import datetime

from sqlbuild.compiler.lineage.types import InferredNullability


@dataclass(frozen=True)
class DatabricksExpressionInferenceProfileTestCase:
    description: str
    expected_sql_analysis_dialect: str
    expected_identifier_limit: int
    expected_rule_results: dict[str, InferredNullability]


@dataclass(frozen=True)
class DatabricksRenderDeleteInsertCursorTestCase:
    description: str
    target: str
    sql: str
    cursor_column: str
    cursor_start: str
    cursor_end: str
    columns: tuple[str, ...] | None
    expected_statements: tuple[str, ...]


@dataclass(frozen=True)
class DatabricksRenderCloneTestCase:
    description: str
    source: str
    target: str
    hard_copy: bool
    expected_statements: tuple[str, ...]
    expected_supports_zero_copy: bool


@dataclass(frozen=True)
class DatabricksRenderDurableCloneTestCase:
    description: str
    source: str
    target: str
    expected_statements: tuple[str, ...]
    expected_supports_durable_clone: bool


@dataclass(frozen=True)
class DatabricksRenderPythonFunctionTestCase:
    description: str
    body_sql: str
    packages: tuple[str, ...]
    expected_statements: tuple[str, ...]


@dataclass(frozen=True)
class DatabricksRenderTableFunctionTestCase:
    description: str
    expected_statements: tuple[str, ...]


@dataclass(frozen=True)
class DatabricksPythonFunctionSupportTestCase:
    description: str
    expected_supports_python_functions: bool


@dataclass(frozen=True)
class DatabricksStringTypeCastRenderingTestCase:
    description: str
    declared_type: str
    expected_loader_fragment: str
    expected_source_cast: str


@dataclass(frozen=True)
class DatabricksPruneSqlTestCase:
    description: str
    database: str | None
    schema: str
    retain_versions: int
    expected_fragments: tuple[str, ...]


@dataclass(frozen=True)
class DatabricksTableFreshnessBatchTestCase:
    description: str
    expected_data_versions: tuple[datetime, ...]
    expected_query_fragments: tuple[str, ...]


@dataclass(frozen=True)
class DatabricksTableFreshnessFallbackTestCase:
    description: str
    expected_data_versions: tuple[datetime, ...]
    expected_query_fragments: tuple[str, ...]
