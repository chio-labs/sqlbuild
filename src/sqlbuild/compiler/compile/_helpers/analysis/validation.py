"""Optional Polyglot-backed SQL syntax validation."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlbuild.compiler.compile._helpers.analysis.columns import (
    _replace_refs_with_stubs,
    substitute_placeholder_defaults,
)
from sqlbuild.compiler.compile.exceptions import CompileInputError
from sqlbuild.compiler.discovery.models import PythonHookEntry, SqlHookEntry
from sqlbuild.compiler.sql_analysis.main.import_polyglot_sql import import_polyglot_sql


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
        cleaned_sql = substitute_placeholder_defaults(
            query_sql=cleaned_sql, placeholders=placeholders
        )

    error_message: str | None = _validate_sql_with_polyglot(sql=cleaned_sql, dialect=dialect)
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


def _validate_sql_with_polyglot(*, sql: str, dialect: str | None) -> str | None:
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
    dialect: str | None = None,
) -> None:
    """Validate hook SQL strings recursively inside supported hook container shapes."""

    if isinstance(value, str):
        effective_label: str = hook_label or hook_name
        _validate_hook_sql_with_message(
            query_sql=value,
            error_prefix=(
                f"Polyglot could not parse model '{model_name}' {effective_label} ({file_path})"
            ),
            placeholders=placeholders,
            dialect=dialect,
        )
        return
    if isinstance(value, SqlHookEntry):
        entry_label: str = (
            f'{hook_name} sql("{value.name}")'
            if value.name is not None
            else f'{hook_name} inline_sql("...")'
        )
        validate_hook_sql_syntax(
            value=value.statement,
            hook_name=hook_name,
            model_name=model_name,
            file_path=value.relative_path or file_path,
            placeholders=placeholders,
            hook_label=hook_label or entry_label,
            dialect=dialect,
        )
        return
    if isinstance(value, PythonHookEntry):
        return
    if isinstance(value, list | tuple):
        hook_index: int
        item: object
        for hook_index, item in enumerate(value):
            item_label: str | None = None
            if isinstance(item, SqlHookEntry):
                item_label = (
                    f'{hook_name}[{hook_index}] sql("{item.name}")'
                    if item.name is not None
                    else f'{hook_name}[{hook_index}] inline_sql("...")'
                )
            elif isinstance(item, str):
                item_label = f'{hook_name}[{hook_index}] inline_sql("...")'
            validate_hook_sql_syntax(
                value=item,
                hook_name=hook_name,
                model_name=model_name,
                file_path=file_path,
                placeholders=placeholders,
                hook_label=item_label,
                dialect=dialect,
            )


def validate_source_expression_syntax(
    *,
    expression: str,
    source_name: str,
    file_path: Path,
) -> None:
    """Validate that a source expression is parseable as a FROM target."""

    from sqlbuild.compiler.references.main._render_source_relation import render_source_relation
    from sqlbuild.spec.contracts.models import SourceEntry

    rendered: str = render_source_relation(
        entry=SourceEntry(name=source_name, expression=expression)
    )
    _validate_sql_syntax_with_message(
        query_sql=f"SELECT * FROM {rendered}",
        error_prefix=f"SQL syntax error in source expression '{source_name}' ({file_path})",
    )


def _validate_sql_syntax_with_message(
    *,
    query_sql: str,
    error_prefix: str,
    placeholders: dict[str, str] | None = None,
    dialect: str | None = None,
) -> None:
    """Parse one SQL expression with Polyglot and raise a contextual error."""

    cleaned_sql: str = _clean_sql_for_validation(
        query_sql=query_sql,
        placeholders=placeholders,
    )
    polyglot_module: Any | None = import_polyglot_sql()
    if polyglot_module is None:
        error_message: str | None = "Polyglot SQL is not installed"
    else:
        try:
            polyglot_module.parse_one(cleaned_sql, dialect=dialect or "generic")
            error_message = None
        except Exception as error:
            error_message = str(error)
    if error_message is not None:
        _raise_sql_validation_error(error_prefix=error_prefix, error_message=error_message)


def _validate_hook_sql_with_message(
    *,
    query_sql: str,
    error_prefix: str,
    placeholders: dict[str, str] | None,
    dialect: str | None,
) -> None:
    """Validate a complete hook execution payload with Polyglot."""

    cleaned_sql: str = _clean_sql_for_validation(
        query_sql=query_sql,
        placeholders=placeholders,
    )
    error_message: str | None = _validate_sql_with_polyglot(sql=cleaned_sql, dialect=dialect)
    if error_message is not None:
        _raise_sql_validation_error(error_prefix=error_prefix, error_message=error_message)


def _clean_sql_for_validation(*, query_sql: str, placeholders: dict[str, str] | None) -> str:
    cleaned_sql: str = _replace_refs_with_stubs(query_sql)
    if placeholders:
        return substitute_placeholder_defaults(
            query_sql=cleaned_sql,
            placeholders=placeholders,
        )
    return cleaned_sql


def _raise_sql_validation_error(*, error_prefix: str, error_message: str) -> None:
    raise CompileInputError(
        f"{error_prefix}: {error_message}\n\n"
        f"To skip SQL validation for this model, add `sql_validation: false` "
        f"to the MODEL header.\n"
        f"To disable project-wide, set `settings.sql_validation: false` "
        f"in sqlbuild_project.toml.\n"
        f"To skip for this run, use `--no-sql-validation`."
    ) from None
