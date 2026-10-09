"""Requests the native SQL-test planning glue reads from compiled objects."""

from __future__ import annotations

from dataclasses import dataclass

from sqlbuild.compiler.compile.models import CompiledModel, CompiledSqlTest


@dataclass(frozen=True)
class NativeSqlTestPlanningRequest:
    """Compiled models and tests to plan, with the adapter facts native planning cannot derive."""

    models: tuple[CompiledModel, ...]
    rendered_model_sql: dict[int, str]
    functions: tuple[tuple[str, str, str, str, str], ...]
    tests: tuple[CompiledSqlTest, ...]
    rendered_test_overrides: dict[int, dict[str, str]]
    sql_analysis_enabled: bool
    sql_analysis_dialect: str | None
    set_difference_operator: str
    requires_derived_table_aliases: bool
    lexical_syntax: dict[str, object]
    render_sql: bool
    include_plan: bool


@dataclass(frozen=True)
class NativeSqlTestChainRequest:
    """Compiled models and the tests whose unmocked model chains to resolve."""

    models: tuple[CompiledModel, ...]
    tests: tuple[CompiledSqlTest, ...]
    lexical_syntax: dict[str, object]
