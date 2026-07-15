"""Local scenario SQL transformation helpers."""

from __future__ import annotations

from typing import Any, NoReturn

from sqlbuild.compiler.sql_analysis.main.import_polyglot_sql import import_polyglot_sql
from sqlbuild.executor.contracts.exceptions import ExecutorInputError
from sqlbuild.executor.scenario.constants import SCENARIO_LOCAL_SQL_TRANSPILE_FAILED


def transpile_sql_for_local_duckdb(
    *,
    sql: str,
    source_dialect: str | None,
    scenario_name: str,
    resource_kind: str,
    resource_name: str,
) -> str:
    """Parse SQL in the source dialect and render DuckDB SQL for local execution."""

    polyglot_module: Any | None = import_polyglot_sql()
    if polyglot_module is None:
        _raise_transpile_error(
            scenario_name=scenario_name,
            resource_kind=resource_kind,
            resource_name=resource_name,
            reason="Polyglot SQL is not installed",
        )
    try:
        transpiled: list[str] = polyglot_module.transpile(
            sql,
            read=source_dialect,
            write="duckdb",
        )
    except Exception as exc:
        _raise_transpile_error(
            scenario_name=scenario_name,
            resource_kind=resource_kind,
            resource_name=resource_name,
            reason=str(exc),
        )
    if len(transpiled) != 1:
        _raise_transpile_error(
            scenario_name=scenario_name,
            resource_kind=resource_kind,
            resource_name=resource_name,
            reason=f"expected one statement, got {len(transpiled)}",
        )
    return transpiled[0]


def _raise_transpile_error(
    *, scenario_name: str, resource_kind: str, resource_name: str, reason: str
) -> NoReturn:
    raise ExecutorInputError(
        f"Local SQL transpilation failed for scenario '{scenario_name}', "
        f"{resource_kind} '{resource_name}': {reason}",
        code=SCENARIO_LOCAL_SQL_TRANSPILE_FAILED,
        help="Rewrite unsupported SQL or adjust the scenario so it can run in DuckDB locally.",
    )


def replace_local_relations(*, sql: str, relation_replacements: dict[str, str]) -> str:
    """Replace planned scenario relation names with local DuckDB relation names."""

    result: str = sql
    original: str
    original: str
    for original in sorted(
        relation_replacements.keys(), key=lambda value: len(value), reverse=True
    ):
        result = result.replace(original, relation_replacements[original])
    return result
