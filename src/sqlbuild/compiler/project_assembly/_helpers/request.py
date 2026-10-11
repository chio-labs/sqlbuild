"""Build the native project assembly request from Python's compile inputs."""

from __future__ import annotations

import os
from collections.abc import Iterable

import sqlbuild._native as _native
from sqlbuild.compiler.authored_values.main._project_var_values import render_project_var_text
from sqlbuild.compiler.compile.models import CompileSqlReference
from sqlbuild.compiler.compile.types import CompileInputsView
from sqlbuild.compiler.project_assembly.constants import (
    BOOLEAN_VARIABLE,
    FALSE_TEXT,
    NATIVE_INT_MAX,
    NATIVE_INT_MIN,
    NONE_VARIABLE,
    OPAQUE_VARIABLE,
    RENDER_LABEL,
    RENDER_RAISES,
    RENDER_REJECTED,
    RENDERED_TEXT,
    TEXT_VARIABLE,
    TRUE_TEXT,
)
from sqlbuild.compiler.project_assembly.types import (
    ProjectRequestRow,
    ReferenceRow,
    SyntaxCheckRow,
    VariableRow,
)
from sqlbuild.spec.contracts.models import DefaultsConfig, TargetConfig


def project_request(
    *,
    inputs: CompileInputsView,
    dialect: str | None,
    syntax_checks: tuple[tuple[tuple[str, dict[str, str] | None], ...], ...],
) -> tuple[ProjectRequestRow, list[Exception | None]]:
    """Return the request row and, per variable, the exception rendering it as text raises."""

    renders: list[tuple[str, str] | Exception | None] = [
        _opaque_render(value=value) for value in inputs.effective_vars.values()
    ]
    target: TargetConfig | None = inputs.effective_target
    defaults: DefaultsConfig = inputs.project_config.defaults
    target_values: tuple[str | None, ...] = (
        (target.database, target.schema, target.loader_schema) if target is not None else ()
    )
    default_values: tuple[str | None, ...] = (
        defaults.database,
        defaults.schema,
        defaults.seed_database,
        defaults.seed_schema,
    )
    seed_values: list[str | None] = []
    for seed_input in inputs.seed_inputs:
        seed_values.extend((seed_input.schema_entry.database, seed_input.schema_entry.schema))
    row: ProjectRequestRow = (
        dialect or "generic",
        (target.database, target.schema, target.loader_schema) if target is not None else None,
        (defaults.database, defaults.schema, defaults.seed_database, defaults.seed_schema),
        [
            _variable_row(name=name, value=value, render=render, index=index)
            for index, ((name, value), render) in enumerate(
                zip(inputs.effective_vars.items(), renders, strict=True)
            )
        ],
        _environment_rows((*target_values, *default_values, *seed_values)),
        [
            (
                model_input.model_file.file_path.stem,
                str(model_input.model_file.relative_path.parent),
                _tag_rows(model_input.config.values.get("tags")),
                _reference_rows(model_input.references),
                _syntax_check_rows(checks),
            )
            for model_input, checks in zip(inputs.model_inputs, syntax_checks, strict=True)
        ],
        [source_input.assembly_row for source_input in inputs.source_inputs],
        [
            (
                seed_input.schema_entry.name,
                list(seed_input.schema_entry.tags),
                seed_input.schema_entry.database,
                seed_input.schema_entry.schema,
            )
            for seed_input in inputs.seed_inputs
        ],
        [function_input.assembly_row for function_input in inputs.sql_function_inputs],
        [audit_input.assembly_row for audit_input in inputs.audit_inputs],
    )
    return row, [render if isinstance(render, Exception) else None for render in renders]


def _tag_rows(value: object) -> list[str]:
    """Model config tags as the project graph indexes them."""

    if isinstance(value, list | tuple):
        return [str(item) for item in value]
    return []


def _environment_rows(values: Iterable[str | None]) -> list[tuple[str, str | None]]:
    """Python's own `os.environ` lookup of every name an `ENV:` template may read."""

    return [
        (name, os.environ.get(name)) for name in _native.environment_template_names(list(values))
    ]


def _variable_row(
    *, name: str, value: object, render: tuple[str, str] | Exception | None, index: int
) -> VariableRow:
    if value is None:
        return (name, NONE_VARIABLE, "", None)
    if type(value) is bool:
        return (name, BOOLEAN_VARIABLE, TRUE_TEXT if value else FALSE_TEXT, None)
    if type(value) is str:
        return (name, TEXT_VARIABLE, value, None)
    if type(value) is int and NATIVE_INT_MIN <= value <= NATIVE_INT_MAX:
        return (name, TEXT_VARIABLE, str(value), None)
    held: tuple[str, str] = (RENDER_RAISES, str(index))
    return (name, OPAQUE_VARIABLE, str(value), held if isinstance(render, Exception) else render)


def _opaque_render(*, value: object) -> tuple[str, str] | Exception | None:
    """`render_project_var_text` for any label: text, the message after the label, or the error."""

    if value is None or type(value) in (bool, str):
        return None
    if type(value) is int and NATIVE_INT_MIN <= value <= NATIVE_INT_MAX:
        return None
    try:
        text: str = render_project_var_text(value=value, label=RENDER_LABEL)
    except ValueError as error:
        message: str = str(error)
        if message.startswith(RENDER_LABEL):
            return (RENDER_REJECTED, message[len(RENDER_LABEL) :])
        return error
    except Exception as error:
        return error
    return (RENDERED_TEXT, text)


def _reference_rows(references: tuple[CompileSqlReference, ...]) -> list[ReferenceRow]:
    return [
        (str(reference.ref_kind), reference.ref_name, reference.ref_package)
        for reference in references
    ]


def _syntax_check_rows(
    checks: tuple[tuple[str, dict[str, str] | None], ...],
) -> list[SyntaxCheckRow]:
    return [(sql, list((placeholders or {}).items())) for sql, placeholders in checks]
