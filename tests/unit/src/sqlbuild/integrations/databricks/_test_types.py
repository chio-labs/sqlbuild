from dataclasses import dataclass

from sqlbuild.compiler.lineage.types import InferredNullability


@dataclass(frozen=True)
class DatabricksExpressionInferenceProfileTestCase:
    description: str
    expected_sqlglot_dialect: str
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
