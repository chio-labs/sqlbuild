"""Test helpers for resolve helper tests."""

from __future__ import annotations

from sqlbuild.adapters.duckdb.classes.duckdb_adapter import DuckDbAdapter
from sqlbuild.compiler.compile.models import CompiledRelationLocation


def build_target(qualified: str | None, name: str) -> CompiledRelationLocation:
    """Build a minimal target for deferred tests."""

    return CompiledRelationLocation(database=None, schema=None, name=name, qualified_name=qualified)


class BracketUdfCallAdapter(DuckDbAdapter):
    def render_udf_call(self, *, target: str, call_suffix_sql: str) -> str:
        arguments_sql: str = call_suffix_sql.removeprefix("(").removesuffix(")")
        return f"{target}[{arguments_sql}]"


class BracketTableFunctionCallAdapter(DuckDbAdapter):
    def render_table_function_call(self, *, target: str, call_suffix_sql: str) -> str:
        arguments_sql: str = call_suffix_sql.removeprefix("(").removesuffix(")")
        return f"TABLE({target}[{arguments_sql}])"
