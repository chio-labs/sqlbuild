"""Local scenario SQL transformation helpers."""

from __future__ import annotations

from typing import Any

from sqlbuild.executor.shared.exceptions import ExecutorInputError
from sqlbuild.shared.constants import SCENARIO_LOCAL_SQL_TRANSPILE_FAILED
from sqlbuild.shared.helpers.sqlglot import import_sqlglot


def transpile_sql_for_local_duckdb(
    *,
    sql: str,
    source_dialect: str | None,
    scenario_name: str,
    resource_kind: str,
    resource_name: str,
) -> str:
    """Parse SQL in the source dialect and render DuckDB SQL for local execution."""

    try:
        sqlglot_module: Any | None = import_sqlglot()
        if sqlglot_module is None:
            raise ImportError("SQLGlot is not installed")
        parsed: Any = (
            sqlglot_module.parse_one(sql, read=source_dialect)
            if source_dialect is not None
            else sqlglot_module.parse_one(sql)
        )
        return parsed.sql(dialect="duckdb")
    except Exception as exc:
        raise ExecutorInputError(
            f"Local SQL transpilation failed for scenario '{scenario_name}', "
            f"{resource_kind} '{resource_name}': {exc}",
            code=SCENARIO_LOCAL_SQL_TRANSPILE_FAILED,
            help="Rewrite unsupported SQL or adjust the scenario so it can run in DuckDB locally.",
        ) from exc


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
