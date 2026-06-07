"""Dependency key derivation helpers for compiled resources."""

from __future__ import annotations

from collections.abc import Iterable

from sqlbuild.compiler.compile.models.core import (
    CompiledObjectKey,
    CompileSqlReference,
)
from sqlbuild.compiler.compile.types import (
    AttachedAuditTargetKind,
    CompiledResourceType,
)
from sqlbuild.shared.types import SqlReferenceKind


def model_build_deps(
    *,
    references: tuple[CompileSqlReference, ...],
    seed_names: frozenset[str] = frozenset(),
) -> tuple[CompiledObjectKey, ...]:
    """Return build graph dependencies implied by model SQL references."""

    if not references:
        return ()
    if len(references) == 1:
        return (_reference_dep(reference=references[0], seed_names=seed_names),)
    return _dedupe_object_keys(
        _reference_dep(reference=reference, seed_names=seed_names) for reference in references
    )


def function_build_deps(
    *,
    references: tuple[CompileSqlReference, ...],
    seed_names: frozenset[str] = frozenset(),
) -> tuple[CompiledObjectKey, ...]:
    """Return build graph dependencies implied by function SQL references."""

    if not references:
        return ()
    if len(references) == 1:
        return (_reference_dep(reference=references[0], seed_names=seed_names),)
    return _dedupe_object_keys(
        _reference_dep(reference=reference, seed_names=seed_names) for reference in references
    )


def audit_scope_deps(
    *,
    references: tuple[CompileSqlReference, ...],
    attached_target_kind: AttachedAuditTargetKind | str | None,
    attached_target_name: str | None,
) -> tuple[CompiledObjectKey, ...]:
    """Return resources that select or gate an audit."""

    deps: list[CompiledObjectKey] = list(model_build_deps(references=references))
    if attached_target_kind is not None and attached_target_name is not None:
        normalized_target_kind: AttachedAuditTargetKind = AttachedAuditTargetKind(
            attached_target_kind
        )
        if normalized_target_kind == AttachedAuditTargetKind.MODEL:
            deps.append(
                CompiledObjectKey(
                    resource_type=CompiledResourceType.MODEL,
                    name=attached_target_name,
                )
            )
        if normalized_target_kind == AttachedAuditTargetKind.SOURCE:
            deps.append(
                CompiledObjectKey(
                    resource_type=CompiledResourceType.SOURCE,
                    name=attached_target_name,
                )
            )
    return _dedupe_object_keys(deps)


def sql_test_scope_deps(*, expected_model_names: tuple[str, ...]) -> tuple[CompiledObjectKey, ...]:
    """Return model targets that select a SQL-native unit test."""

    if not expected_model_names:
        return ()
    if len(expected_model_names) == 1:
        return (
            CompiledObjectKey(
                resource_type=CompiledResourceType.MODEL, name=expected_model_names[0]
            ),
        )
    return _dedupe_object_keys(
        CompiledObjectKey(resource_type=CompiledResourceType.MODEL, name=model_name)
        for model_name in expected_model_names
    )


def _reference_dep(
    *, reference: CompileSqlReference, seed_names: frozenset[str] = frozenset()
) -> CompiledObjectKey:
    if reference.ref_kind == SqlReferenceKind.SOURCE:
        return CompiledObjectKey(
            resource_type=CompiledResourceType.SOURCE,
            name=reference.ref_name,
        )
    if reference.ref_kind == SqlReferenceKind.SEED:
        return CompiledObjectKey(
            resource_type=CompiledResourceType.SEED,
            name=reference.ref_name,
        )
    if reference.ref_kind == SqlReferenceKind.DBT_REF:
        return CompiledObjectKey(
            resource_type=CompiledResourceType.DBT_REF,
            name=(
                f"{reference.ref_package}.{reference.ref_name}"
                if reference.ref_package is not None
                else reference.ref_name
            ),
        )
    if reference.ref_kind in {SqlReferenceKind.UDF, SqlReferenceKind.TABLE_FUNCTION}:
        return CompiledObjectKey(
            resource_type=CompiledResourceType.FUNCTION,
            name=reference.ref_name,
        )
    return CompiledObjectKey(
        resource_type=CompiledResourceType.MODEL,
        name=reference.ref_name,
    )


def _dedupe_object_keys(keys: Iterable[CompiledObjectKey]) -> tuple[CompiledObjectKey, ...]:
    deduped_keys: list[CompiledObjectKey] = []
    seen_keys: set[CompiledObjectKey] = set()
    key: CompiledObjectKey
    for key in keys:
        if key in seen_keys:
            continue
        seen_keys.add(key)
        deduped_keys.append(key)
    return tuple(deduped_keys)
