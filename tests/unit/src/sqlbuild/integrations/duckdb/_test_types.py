from dataclasses import dataclass

from sqlbuild.compiler.lineage.types import InferredNullability


@dataclass(frozen=True)
class DuckDbExpressionInferenceProfileTestCase:
    description: str
    expected_sqlglot_dialect: str
    expected_rule_results: dict[str, InferredNullability]


@dataclass(frozen=True)
class DuckDbRenderCursorBoundLiteralTestCase:
    description: str
    value: str
    cursor_type: str | None
    expected_literal: str


@dataclass(frozen=True)
class DuckDbRenderTableFunctionTestCase:
    description: str
    expected_statements: tuple[str, ...]
