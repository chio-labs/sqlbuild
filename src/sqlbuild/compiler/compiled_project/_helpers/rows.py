"""Rows producers hand the native compiled project when they retain a resource's facts."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import cast

import sqlbuild._native as _native
from sqlbuild.compiler.compile.models import (
    CompiledModel,
    CompiledProject,
    CompileModelConfig,
    CompileModelInput,
    CompileSqlReference,
    DynamicColumnContractProof,
)
from sqlbuild.compiler.discovery.models import ConstantDeclaration, EnumDeclaration
from sqlbuild.spec.contracts.models import SchemaModelEntry
from sqlbuild.sql_values.models import SqlValue
from sqlbuild.sql_values.types import SqlValueKind


@dataclass(frozen=True)
class _ModelDeclarations:
    enum_columns: tuple[str, ...]
    enums: tuple[EnumDeclaration, ...]
    constants: tuple[ConstantDeclaration, ...]


def record_model_inputs_impl(
    *, project: _native.NativeCompiledProject, model_inputs: tuple[CompileModelInput, ...]
) -> int:
    """Retain each model the compile-input stage produced, in production order; return how many."""

    for model_input in model_inputs:
        project.record_model(
            _model_row(
                identity=(
                    model_input.model_file.file_path.stem,
                    model_input.model_file.relative_path.as_posix(),
                    model_input.query_sql,
                    model_input.model_file.query_sql,
                    model_input.model_file.contents,
                ),
                config=model_input.config,
                references=model_input.references,
                schema_entry=model_input.schema_entry,
                declarations=_ModelDeclarations(
                    enum_columns=tuple(model_input.enum_columns),
                    enums=model_input.enum_declarations,
                    constants=model_input.constant_declarations,
                ),
            )
        )
    return len(model_inputs)


def record_model_analyses_impl(
    *, project: _native.NativeCompiledProject, models: tuple[CompiledModel, ...]
) -> int:
    """Transfer each assembled model's typed analysis to its retained facts; return how many."""

    transferred: int = 0
    for model in models:
        proof: DynamicColumnContractProof | None = model.dynamic_column_contract
        transferred += project.record_model_analysis(
            model.name,
            [(column.name, column.type) for column in (model.inferred_columns or ())],
            None
            if proof is None
            else (
                proof.output_proven,
                proof.bare_dynamic_pivot,
                [(family.name.casefold(), family.inferred_type) for family in proof.families],
            ),
        )
    return transferred


def hand_built_project_impl(project: CompiledProject) -> _native.NativeCompiledProject:
    """A native project for a `CompiledProject` built without the compile-input stage."""

    native: _native.NativeCompiledProject = _native.NativeCompiledProject()
    for model in project.models:
        native.record_model(
            _model_row(
                identity=(
                    model.name,
                    model.relative_path.as_posix(),
                    model.query_sql,
                    model.authored_query_sql,
                    model.authored_sql,
                ),
                config=model.config,
                references=model.references,
                schema_entry=model.schema_entry,
                declarations=_ModelDeclarations(
                    enum_columns=tuple(model.enum_columns),
                    enums=model.enum_declarations,
                    constants=model.constant_declarations,
                ),
            )
        )
    _ = record_model_analyses_impl(project=native, models=project.models)
    return native


def enum_row(declaration: EnumDeclaration) -> tuple[object, ...]:
    """An enum declaration as the native project row."""

    return (
        declaration.name,
        declaration.relative_path.as_posix(),
        [(member.name, member.value) for member in declaration.members],
        None,
        None,
        None,
    )


def constant_row(declaration: ConstantDeclaration) -> tuple[object, ...]:
    """A constant declaration as the native project row, its value made JSON-safe."""

    return (
        declaration.name,
        declaration.relative_path.as_posix(),
        [],
        typed_value_payload(declaration.value),
        declaration.logical_type.display_name,
        declaration.render_as.value if declaration.render_as is not None else None,
    )


def typed_value_payload(value: SqlValue) -> object:
    """A typed SQL value as the plain value native consumers read."""

    if value.kind == SqlValueKind.DECIMAL:
        return str(cast(Decimal, value.value))
    if value.kind in {
        SqlValueKind.STRING,
        SqlValueKind.INTEGER,
        SqlValueKind.BOOLEAN,
        SqlValueKind.FLOAT,
        SqlValueKind.NULL,
    }:
        return value.value
    if value.kind in {SqlValueKind.LIST, SqlValueKind.SET}:
        return [typed_value_payload(item) for item in cast(tuple[SqlValue, ...], value.value)]
    return {
        key: typed_value_payload(item)
        for key, item in cast(tuple[tuple[str, SqlValue], ...], value.value)
    }


def _model_row(
    *,
    identity: tuple[str, str, str, str, str],
    config: CompileModelConfig,
    references: tuple[CompileSqlReference, ...],
    schema_entry: SchemaModelEntry | None,
    declarations: _ModelDeclarations,
) -> tuple[object, ...]:
    return (
        identity,
        (config.values, list(config.model_header_keys), config.layer_schema),
        [
            (str(reference.ref_kind), reference.ref_name, reference.ref_package)
            for reference in references
        ],
        _schema_row(schema_entry),
        list(declarations.enum_columns),
        (
            [enum_row(declaration) for declaration in declarations.enums],
            [constant_row(declaration) for declaration in declarations.constants],
        ),
    )


def _schema_row(entry: SchemaModelEntry | None) -> object:
    if entry is None:
        return None
    return (
        len(entry.audits),
        [
            (column.name, column.type, column.nullable, len(column.audits))
            for column in entry.columns
        ],
        [
            (
                family.name.casefold(),
                family.name,
                family.pivot_column,
                family.value_column,
                family.aggregate,
                family.type,
                family.name_pattern,
            )
            for family in entry.dynamic_columns
        ],
    )
