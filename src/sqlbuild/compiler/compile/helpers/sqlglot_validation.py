"""Optional SQLGlot-backed SQL syntax validation for model queries."""

from __future__ import annotations

from importlib import import_module
from pathlib import Path
from typing import Any

from sqlbuild.compiler.compile.exceptions import CompileInputError
from sqlbuild.compiler.compile.helpers.sqlglot_columns import (
    _replace_refs_with_stubs,
    substitute_placeholder_defaults,
)


def validate_sql_syntax(
    *,
    query_sql: str,
    model_name: str,
    file_path: Path,
    placeholders: dict[str, str] | None = None,
) -> None:
    """Validate that the model query SQL is parseable by SQLGlot.

    Raises CompileInputError if the SQL cannot be parsed. Silently returns
    if SQLGlot is not installed.
    """

    try:
        sqlglot_module: Any = import_module("sqlglot")
    except ModuleNotFoundError:
        return

    cleaned_sql: str = _replace_refs_with_stubs(query_sql)
    if placeholders:
        cleaned_sql = substitute_placeholder_defaults(cleaned_sql, placeholders)

    try:
        sqlglot_module.parse_one(cleaned_sql)
    except Exception as exc:
        raise CompileInputError(
            f"SQL syntax error in model '{model_name}' ({file_path}): {exc}\n\n"
            f"To skip SQL validation for this model, add `sql_validation: false` "
            f"to the MODEL header.\n"
            f"To disable project-wide, set `settings.sql_validation: false` "
            f"in sqlbuild_project.yml.\n"
            f"To skip for this run, use `--no-sql-validation`."
        ) from None
