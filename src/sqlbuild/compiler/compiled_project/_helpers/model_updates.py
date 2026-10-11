"""Record what later compile stages finish for a model, natively when its owner holds it."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import fields, replace
from typing import Any, cast

import sqlbuild._native as _native
from sqlbuild.compiler.compile.models import (
    CompiledAudit,
    CompiledFunction,
    CompiledModel,
    CompiledProject,
    CompiledSeed,
    CompiledSource,
    CompileProjectInputs,
    CompilerDiagnostic,
    InferredColumn,
)
from sqlbuild.compiler.compile.types import (
    CompiledAuditView,
    CompiledFunctionView,
    CompiledModelView,
    CompiledProjectView,
    CompiledSeedView,
    CompiledSourceView,
    CompileInputsView,
)


def compiled_model_record_impl(model: CompiledModelView) -> CompiledModel:
    """The model as a `CompiledModel`, projected from its owner when it is a native view."""

    if isinstance(model, CompiledModel):
        return model
    return CompiledModel(
        **{field.name: getattr(model, field.name) for field in fields(CompiledModel)}
    )


def with_binding_diagnostics_impl(
    *, model: CompiledModelView, diagnostics: tuple[CompilerDiagnostic, ...]
) -> CompiledModelView:
    """The model with these final binding diagnostics."""

    if isinstance(model, CompiledModel):
        return replace(model, binding_diagnostics=diagnostics)
    return cast(_native.NativeCompiledModel, model).with_binding_diagnostics(diagnostics)


def with_type_recovery_impl(
    *,
    model: CompiledModelView,
    diagnostics: tuple[CompilerDiagnostic, ...],
    poisoned: frozenset[tuple[str, str]],
) -> CompiledModelView:
    """The model with its recovered bindings and its poisoned outputs' types forgotten."""

    if not isinstance(model, CompiledModel):
        native: _native.NativeCompiledModel = cast(_native.NativeCompiledModel, model)
        return native.with_type_recovery(
            diagnostics, [column for name, column in poisoned if name == native.name]
        )
    columns: tuple[InferredColumn, ...] | None = None
    if model.inferred_columns is not None:
        columns = tuple(
            replace(column, type=None) if (model.name, column.name) in poisoned else column
            for column in model.inferred_columns
        )
    unchecked: frozenset[str] = frozenset(column for name, column in poisoned if name == model.name)
    return replace(
        model,
        binding_diagnostics=diagnostics,
        inferred_columns=columns,
        unchecked_output_columns=unchecked,
    )


def with_target_defaults_impl(
    *,
    model: _native.NativeCompiledModel,
    defaults: tuple[str | None, str | None],
    render_qualified_name: Callable[..., str | None],
) -> CompiledModelView:
    """The model with the adapter's `(schema, database)` defaults filled into its destination."""

    return model.with_target_defaults(defaults, render_qualified_name)


def compiled_project_record_impl(
    *, project: CompiledProjectView, include_sql_expansions: bool = True
) -> CompiledProject:
    """The project as a `CompiledProject`, projected from its owner when it is a native view."""

    if isinstance(project, CompiledProject):
        return project if include_sql_expansions else replace(project, sql_expansions={})
    fields: dict[str, Any] = cast(_native.NativeProjectView, project).fields(include_sql_expansions)
    fields["seeds"] = tuple(map(compiled_seed_record_impl, fields["seeds"]))
    fields["sources"] = tuple(map(compiled_source_record_impl, fields["sources"]))
    fields["functions"] = tuple(map(compiled_function_record_impl, fields["functions"]))
    fields["audits"] = tuple(map(compiled_audit_record_impl, fields["audits"]))
    return CompiledProject(**fields)


def compiled_audit_record_impl(audit: CompiledAuditView) -> CompiledAudit:
    """The audit as a `CompiledAudit`, projected from its owner when it is a native view."""

    if isinstance(audit, CompiledAudit):
        return audit
    return CompiledAudit(
        key=audit.key,
        scope_deps=audit.scope_deps,
        name=audit.name,
        definition_name=audit.definition_name,
        audit_file=audit.audit_file,
        audit_block=audit.audit_block,
        sql_body=audit.sql_body,
        evaluation_mode=audit.evaluation_mode,
        measurement_contract=audit.measurement_contract,
        thresholds=audit.thresholds,
        minimum_samples=audit.minimum_samples,
        measure_sql=audit.measure_sql,
        evidence_sql=audit.evidence_sql,
        evidence_limit=audit.evidence_limit,
        references=audit.references,
        attached_target_kind=audit.attached_target_kind,
        attached_target_name=audit.attached_target_name,
        attached_column_name=audit.attached_column_name,
        severity=audit.severity,
        run_scope=audit.run_scope,
        always_run=audit.always_run,
        description=audit.description,
    )


def compiled_function_record_impl(function: CompiledFunctionView) -> CompiledFunction:
    """The function as a `CompiledFunction`, projected from its owner when it is a native view."""

    if isinstance(function, CompiledFunction):
        return function
    return CompiledFunction(
        key=function.key,
        deps=function.deps,
        name=function.name,
        relative_path=function.relative_path,
        arguments=function.arguments,
        returns=function.returns,
        body_sql=function.body_sql,
        destination=function.destination,
        fingerprint_destination=function.fingerprint_destination,
        return_columns=function.return_columns,
        references=function.references,
        language=function.language,
        source_file_path=function.source_file_path,
        runtime_version=function.runtime_version,
        entry_point=function.entry_point,
        packages=function.packages,
        tags=function.tags,
        description=function.description,
    )


def compiled_source_record_impl(source: CompiledSourceView) -> CompiledSource:
    """The source as a `CompiledSource`, projected from its owner when it is a native view."""

    if isinstance(source, CompiledSource):
        return source
    return CompiledSource(
        key=source.key,
        deps=source.deps,
        name=source.name,
        source_entry=source.source_entry,
        source_file=source.source_file,
    )


def compiled_seed_record_impl(seed: CompiledSeedView) -> CompiledSeed:
    """The seed as a `CompiledSeed`, projected from its owner when it is a native view."""

    if isinstance(seed, CompiledSeed):
        return seed
    return CompiledSeed(
        key=seed.key,
        deps=seed.deps,
        name=seed.name,
        seed_file=seed.seed_file,
        schema_entry=seed.schema_entry,
        schema_file=seed.schema_file,
        destination=seed.destination,
        external=seed.external,
    )


def project_with_impl(*, project: CompiledProjectView, **changes: Any) -> CompiledProjectView:
    """The project with `changes`; a native view shares its owner's models."""

    if isinstance(project, CompiledProject):
        return replace(project, **changes)
    return cast(_native.NativeProjectView, project).with_changes(**changes)


def inputs_with_impl(*, inputs: CompileInputsView, **changes: Any) -> CompileInputsView:
    """The compile inputs with `changes`; a native view shares its owner's model inputs."""

    if isinstance(inputs, CompileProjectInputs):
        return replace(inputs, **changes)
    return cast(_native.NativeInputsView, inputs).with_changes(**changes)


def compile_inputs_view_impl(
    *, fields: dict[str, Any], native_project: _native.NativeCompiledProject | None
) -> CompileInputsView:
    """The native owner's inputs view when it holds every model input; else a record."""

    if native_project is not None and all(
        isinstance(model, _native.NativeModelInput) for model in fields["model_inputs"]
    ):
        return native_project.inputs_view(fields)
    return CompileProjectInputs(**fields, native_project=native_project)
