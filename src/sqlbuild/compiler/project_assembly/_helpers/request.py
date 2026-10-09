"""Build the native project assembly request from Python's compile inputs."""

from __future__ import annotations

import os

from sqlbuild.compiler.compile.models import CompileProjectInputs, CompileSqlReference
from sqlbuild.compiler.project_assembly.constants import (
    BOOLEAN_VARIABLE,
    FALSE_TEXT,
    NATIVE_INT_MAX,
    NATIVE_INT_MIN,
    NONE_VARIABLE,
    TEXT_VARIABLE,
    TRUE_TEXT,
    UNSUPPORTED_VARIABLE,
)
from sqlbuild.compiler.project_assembly.types import (
    AuditRow,
    ProjectRequestRow,
    ReferenceRow,
    SyntaxCheckRow,
    VariableRow,
)
from sqlbuild.spec.contracts.models import DefaultsConfig, TargetConfig


def project_request(
    *,
    inputs: CompileProjectInputs,
    dialect: str | None,
    syntax_checks: tuple[tuple[tuple[str, dict[str, str] | None], ...], ...],
) -> ProjectRequestRow:
    """Return the request row; `syntax_checks` holds each model's SQL Python would validate."""

    target: TargetConfig | None = inputs.effective_target
    defaults: DefaultsConfig = inputs.project_config.defaults
    return (
        dialect or "generic",
        (target.database, target.schema, target.loader_schema) if target is not None else None,
        (defaults.database, defaults.schema, defaults.seed_database, defaults.seed_schema),
        [_variable_row(name=name, value=value) for name, value in inputs.effective_vars.items()],
        list(os.environ.items()),
        [
            (_reference_rows(model_input.references), _syntax_check_rows(checks))
            for model_input, checks in zip(inputs.model_inputs, syntax_checks, strict=True)
        ],
        [
            (
                source_input.source_entry.name,
                source_input.source_entry.loader is not None,
                source_input.source_entry.database,
                source_input.source_entry.schema,
            )
            for source_input in inputs.source_inputs
        ],
        [
            (
                seed_input.schema_entry.name,
                seed_input.schema_entry.database,
                seed_input.schema_entry.schema,
            )
            for seed_input in inputs.seed_inputs
        ],
        [
            _reference_rows(function_input.references)
            for function_input in inputs.sql_function_inputs
        ],
        [
            _audit_row(
                references=audit_input.references,
                attached_kind=audit_input.attached_target_kind,
                attached_name=audit_input.attached_target_name,
            )
            for audit_input in inputs.audit_inputs
        ],
    )


def _variable_row(*, name: str, value: object) -> VariableRow:
    if value is None:
        return (name, NONE_VARIABLE, "")
    if type(value) is bool:
        return (name, BOOLEAN_VARIABLE, TRUE_TEXT if value else FALSE_TEXT)
    if type(value) is str:
        return (name, TEXT_VARIABLE, value)
    if type(value) is int and NATIVE_INT_MIN <= value <= NATIVE_INT_MAX:
        return (name, TEXT_VARIABLE, str(value))
    return (name, UNSUPPORTED_VARIABLE, "")


def _reference_rows(references: tuple[CompileSqlReference, ...]) -> list[ReferenceRow]:
    return [
        (str(reference.ref_kind), reference.ref_name, reference.ref_package)
        for reference in references
    ]


def _syntax_check_rows(
    checks: tuple[tuple[str, dict[str, str] | None], ...],
) -> list[SyntaxCheckRow]:
    return [(sql, list((placeholders or {}).items())) for sql, placeholders in checks]


def _audit_row(
    *,
    references: tuple[CompileSqlReference, ...],
    attached_kind: object,
    attached_name: str | None,
) -> AuditRow:
    attached: tuple[str, str] | None = (
        (str(attached_kind), attached_name)
        if attached_kind is not None and attached_name is not None
        else None
    )
    return (_reference_rows(references), attached)
