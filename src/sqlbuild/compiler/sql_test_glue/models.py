"""Requests and results of the native SQL-test glue, read from compiled objects."""

from __future__ import annotations

from dataclasses import dataclass

from sqlbuild.compiler.compile.models import (
    CompiledModel,
    CompiledSqlTest,
    CompileModelInput,
    CompilerDiagnostic,
    CompileSqlTestInput,
)


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


@dataclass(frozen=True)
class NativeSqlTestAssemblyRequest:
    """The project's model inputs and the SQL test inputs whose compiled facts to assemble."""

    model_inputs: tuple[CompileModelInput, ...]
    test_inputs: tuple[CompileSqlTestInput, ...]
    lexical_syntax: dict[str, object]


@dataclass(frozen=True)
class NativeSqlTestAssembly:
    """One natively assembled test and the keyed diagnostics to report before it."""

    test: CompiledSqlTest
    diagnostics: tuple[tuple[tuple[str, ...], CompilerDiagnostic], ...]
