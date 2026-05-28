from dataclasses import dataclass


@dataclass(frozen=True)
class BaseAdapterPythonFunctionSupportTestCase:
    description: str
    expected_error_fragment: str


@dataclass(frozen=True)
class BaseAdapterExpressionInferenceProfileTestCase:
    description: str
    expected_sqlglot_dialect: str | None
    expected_function_rules_count: int


@dataclass(frozen=True)
class BaseAdapterSqlglotDialectTestCase:
    description: str
    expected_sqlglot_dialect: str | None


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
