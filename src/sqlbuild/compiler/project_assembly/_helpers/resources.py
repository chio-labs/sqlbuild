"""Materialise the native project assembly result as the objects Python's assembly builds."""

from __future__ import annotations

from dataclasses import replace

from sqlbuild.compiler.compile.constants import COMPILE_INPUT_READS
from sqlbuild.compiler.compile.models import (
    CompiledObjectKey,
    CompiledRelationLocation,
    CompileProjectInputs,
    CompileSeedInput,
    CompileSourceInput,
)
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.project_assembly.constants import ENVIRONMENT_READ
from sqlbuild.compiler.project_assembly.models import NativeProjectResources
from sqlbuild.compiler.project_assembly.types import (
    NamespaceRow,
    ObjectKeyRow,
    ProjectResourcesRow,
)
from sqlbuild.spec.contracts.models import SourceEntry


def project_resources(
    *, inputs: CompileProjectInputs, row: ProjectResourcesRow
) -> NativeProjectResources:
    """Return the resource facts the native row describes, in input order."""

    model_deps, source_namespaces, seed_namespaces, function_deps, audit_deps, reads, syntax = row
    _ = [_replay_read(kind=kind, name=name) for kind, name in reads]
    return NativeProjectResources(
        model_deps=tuple(_keys(keys) for keys in model_deps),
        model_syntax_valid=tuple(syntax),
        source_entries=tuple(
            _source_entry(source_input=source_input, namespace=namespace)
            for source_input, namespace in zip(inputs.source_inputs, source_namespaces, strict=True)
        ),
        seed_destinations=tuple(
            _seed_destination(seed_input=seed_input, namespace=namespace)
            for seed_input, namespace in zip(inputs.seed_inputs, seed_namespaces, strict=True)
        ),
        function_deps=tuple(_keys(keys) for keys in function_deps),
        audit_scope_deps=tuple(_keys(keys) for keys in audit_deps),
    )


def _replay_read(*, kind: str, name: str) -> None:
    if kind == ENVIRONMENT_READ:
        COMPILE_INPUT_READS.environment_read(name)
    else:
        COMPILE_INPUT_READS.context_read(name)


def _keys(rows: list[ObjectKeyRow]) -> tuple[CompiledObjectKey, ...]:
    return tuple(
        CompiledObjectKey(resource_type=CompiledResourceType(kind), name=name)
        for kind, name in rows
    )


def _source_entry(
    *, source_input: CompileSourceInput, namespace: tuple[str | None, str | None] | None
) -> SourceEntry:
    if namespace is None:
        return source_input.source_entry
    return replace(source_input.source_entry, database=namespace[0], schema=namespace[1])


def _seed_destination(
    *, seed_input: CompileSeedInput, namespace: NamespaceRow
) -> CompiledRelationLocation:
    database, schema, logical_database, logical_schema = namespace
    return CompiledRelationLocation(
        database=database,
        schema=schema,
        name=seed_input.schema_entry.name,
        qualified_name=None,
        logical_schema=logical_schema,
        logical_database=logical_database,
    )
