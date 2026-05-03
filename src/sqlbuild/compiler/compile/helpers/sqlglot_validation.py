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

_VALID_HOOK_ROOT_KEYS: frozenset[str] = frozenset(
    {
        "select",
        "union",
        "insert",
        "update",
        "delete",
        "merge",
        "create",
        "alter",
        "drop",
        "truncate",
        "grant",
        "revoke",
        "set",
        "call",
        "copy",
        "use",
        "attach",
        "detach",
        "analyze",
        "vacuum",
        "comment",
        "transaction",
        "commit",
        "rollback",
        "command",
    }
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


def validate_hook_sql_syntax(
    *,
    value: object,
    hook_name: str,
    model_name: str,
    file_path: Path,
    placeholders: dict[str, str] | None = None,
) -> None:
    """Validate hook SQL strings recursively inside supported hook container shapes."""

    if isinstance(value, str):
        _validate_sql_syntax_with_message(
            query_sql=value,
            error_prefix=f"SQL syntax error in {hook_name} for model '{model_name}' ({file_path})",
            placeholders=placeholders,
            require_hook_statement=True,
        )
        return
    if isinstance(value, list | tuple):
        item: object
        for item in value:
            validate_hook_sql_syntax(
                value=item,
                hook_name=hook_name,
                model_name=model_name,
                file_path=file_path,
                placeholders=placeholders,
            )


def _validate_sql_syntax_with_message(
    *,
    query_sql: str,
    error_prefix: str,
    placeholders: dict[str, str] | None = None,
    require_hook_statement: bool = False,
) -> None:
    """Parse SQL with SQLGlot and raise CompileInputError with a custom message."""

    try:
        sqlglot_module: Any = import_module("sqlglot")
    except ModuleNotFoundError:
        return

    cleaned_sql: str = _replace_refs_with_stubs(query_sql)
    if placeholders:
        cleaned_sql = substitute_placeholder_defaults(cleaned_sql, placeholders)

    try:
        parsed: Any = sqlglot_module.parse_one(cleaned_sql)
        if require_hook_statement and parsed.key not in _VALID_HOOK_ROOT_KEYS:
            raise ValueError(
                "hook SQL must be a valid executable SQL statement, "
                f"but this parsed as a non-statement expression ('{parsed.key}')"
            )
    except Exception as exc:
        raise CompileInputError(
            f"{error_prefix}: {exc}\n\n"
            f"To skip SQL validation for this model, add `sql_validation: false` "
            f"to the MODEL header.\n"
            f"To disable project-wide, set `settings.sql_validation: false` "
            f"in sqlbuild_project.yml.\n"
            f"To skip for this run, use `--no-sql-validation`."
        ) from None
