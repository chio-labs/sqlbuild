"""Optional Polyglot-backed SQL syntax validation for model queries."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlbuild.compiler.compile.exceptions import CompileInputError
from sqlbuild.compiler.compile.helpers.analysis.columns import (
    _replace_refs_with_stubs,
    substitute_placeholder_defaults,
)
from sqlbuild.shared.helpers.polyglot import import_polyglot_sql
from sqlbuild.shared.models import PythonHookEntry, SqlHookEntry

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
    dialect: str | None = None,
) -> None:
    """Validate that the model query SQL is parseable by Polyglot."""

    cleaned_sql: str = _replace_refs_with_stubs(query_sql)
    if placeholders:
        cleaned_sql = substitute_placeholder_defaults(cleaned_sql, placeholders)

    error_message: str | None = _validate_sql_with_polyglot(cleaned_sql, dialect=dialect)
    if error_message is None:
        return
    raise CompileInputError(
        f"SQL syntax error in model '{model_name}' ({file_path}): {error_message}\n\n"
        f"To skip SQL validation for this model, add `sql_validation: false` "
        f"to the MODEL header.\n"
        f"To disable project-wide, set `settings.sql_validation: false` "
        f"in sqlbuild_project.toml.\n"
        f"To skip for this run, use `--no-sql-validation`."
    ) from None


def _validate_sql_with_polyglot(sql: str, *, dialect: str | None) -> str | None:
    polyglot_module: Any | None = import_polyglot_sql()
    if polyglot_module is None:
        return "Polyglot SQL is not installed"
    try:
        result: Any = polyglot_module.validate(sql, dialect=dialect or "generic")
    except Exception as error:
        return str(error)
    if result:
        return None
    error_message: str = "invalid SQL"
    errors: object = getattr(result, "errors", ())
    if isinstance(errors, list) and errors:
        error_message = str(getattr(errors[0], "message", error_message))
    return error_message


def validate_function_sql_syntax(
    *,
    body_sql: str,
    function_name: str,
    file_path: Path,
    placeholders: dict[str, str] | None = None,
) -> None:
    """Validate that a SQL function body is parseable by Polyglot."""

    _validate_sql_syntax_with_message(
        query_sql=body_sql,
        error_prefix=f"SQL syntax error in function '{function_name}' ({file_path})",
        placeholders=placeholders,
    )


def validate_hook_sql_syntax(
    *,
    value: object,
    hook_name: str,
    model_name: str,
    file_path: Path,
    placeholders: dict[str, str] | None = None,
    hook_label: str | None = None,
) -> None:
    """Validate hook SQL strings recursively inside supported hook container shapes."""

    if isinstance(value, str):
        effective_label: str = hook_label or hook_name
        _validate_sql_syntax_with_message(
            query_sql=value,
            error_prefix=f"model '{model_name}' {effective_label} has invalid SQL ({file_path})",
            placeholders=placeholders,
            require_hook_statement=True,
        )
        return
    if isinstance(value, SqlHookEntry):
        validate_hook_sql_syntax(
            value=value.statement,
            hook_name=hook_name,
            model_name=model_name,
            file_path=file_path,
            placeholders=placeholders,
            hook_label=hook_label or f'{hook_name} sql("...")',
        )
        return
    if isinstance(value, PythonHookEntry):
        return
    if isinstance(value, list | tuple):
        hook_index: int
        item: object
        for hook_index, item in enumerate(value):
            item_label: str | None = None
            if isinstance(item, SqlHookEntry | str):
                item_label = f'{hook_name}[{hook_index}] sql("...")'
            validate_hook_sql_syntax(
                value=item,
                hook_name=hook_name,
                model_name=model_name,
                file_path=file_path,
                placeholders=placeholders,
                hook_label=item_label,
            )


def validate_source_expression_syntax(
    *,
    expression: str,
    source_name: str,
    file_path: Path,
) -> None:
    """Validate that a source expression is parseable as a FROM target."""

    from sqlbuild.compiler.shared.helpers.sources import render_source_relation
    from sqlbuild.spec.models.source import SourceEntry

    rendered: str = render_source_relation(SourceEntry(name=source_name, expression=expression))
    _validate_sql_syntax_with_message(
        query_sql=f"SELECT * FROM {rendered}",
        error_prefix=f"SQL syntax error in source expression '{source_name}' ({file_path})",
    )


def _validate_sql_syntax_with_message(
    *,
    query_sql: str,
    error_prefix: str,
    placeholders: dict[str, str] | None = None,
    require_hook_statement: bool = False,
) -> None:
    """Parse SQL with Polyglot and raise CompileInputError with a custom message."""

    cleaned_sql: str = _replace_refs_with_stubs(query_sql)
    if placeholders:
        cleaned_sql = substitute_placeholder_defaults(cleaned_sql, placeholders)

    polyglot_module: Any | None = import_polyglot_sql()
    if polyglot_module is None:
        parsed_error: str = "Polyglot SQL is not installed"
        parsed: Any | None = None
    else:
        parsed_error = ""
        parsed = None
        try:
            parsed = polyglot_module.parse_one(cleaned_sql, dialect="generic")
        except Exception as exc:
            parsed_error = str(exc)
    if parsed is None:
        raise CompileInputError(
            f"{error_prefix}: {parsed_error}\n\n"
            f"To skip SQL validation for this model, add `sql_validation: false` "
            f"to the MODEL header.\n"
            f"To disable project-wide, set `settings.sql_validation: false` "
            f"in sqlbuild_project.toml.\n"
            f"To skip for this run, use `--no-sql-validation`."
        ) from None

    parsed_kind: str = str(getattr(parsed, "kind", ""))
    if require_hook_statement and parsed_kind not in _VALID_HOOK_ROOT_KEYS:
        raise CompileInputError(
            f"{error_prefix}: hook SQL must be a valid executable SQL statement, "
            f"but this parsed as a non-statement expression ('{parsed_kind}')\n\n"
            f"To skip SQL validation for this model, add `sql_validation: false` "
            f"to the MODEL header.\n"
            f"To disable project-wide, set `settings.sql_validation: false` "
            f"in sqlbuild_project.toml.\n"
            f"To skip for this run, use `--no-sql-validation`."
        )
