from dataclasses import dataclass


@dataclass(frozen=True)
class BaseAdapterPythonFunctionSupportTestCase:
    description: str
    expected_error_fragment: str


@dataclass(frozen=True)
class BaseAdapterExpressionInferenceProfileTestCase:
    description: str
    expected_sql_analysis_dialect: str | None
    expected_function_rules_count: int


@dataclass(frozen=True)
class BaseAdapterSqlAnalysisDialectTestCase:
    description: str
    expected_sql_analysis_dialect: str | None


@dataclass(frozen=True)
class BaseAdapterIdentifierLimitTestCase:
    description: str
    expected_identifier_limit: int


@dataclass(frozen=True)
class BaseAdapterDurableCloneTestCase:
    description: str
    source: str
    target: str
    expected_supports_durable_clone: bool
    expected_statements: tuple[str, ...]


@dataclass(frozen=True)
class BaseAdapterMetadataSqlTestCase:
    description: str
    database: str
    schema: str
    name: str
    expected_sql: tuple[str, ...]


@dataclass(frozen=True)
class BaseAdapterRelationMaxCursorTestCase:
    description: str
    rows: tuple[tuple[object, ...], ...]
    relation: str
    cursor_column: str
    expected_value: object | None
    expected_sql: str
