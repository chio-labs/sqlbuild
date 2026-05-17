"""Audit attachment resolution and scheduling validation."""

from __future__ import annotations

from sqlbuild.compiler.auditing.types import (
    AuditAttachmentKind,
    AuditRunScope,
)
from sqlbuild.compiler.compile.models.core import (
    CompiledAudit,
    CompiledObjectKey,
    CompileSqlReference,
)
from sqlbuild.compiler.compile.types import (
    AttachedAuditTargetKind,
    CompiledResourceType,
)
from sqlbuild.compiler.planner.exceptions import PlannerInputError
from sqlbuild.compiler.planner.helpers.graph import expand_downstream
from sqlbuild.compiler.planner.types import MaterializationType
from sqlbuild.shared.types import SqlReferenceKind


def resolve_attachment_kind(
    *,
    audit: CompiledAudit,
    upstream_deps: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]],
    downstream_deps: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]],
) -> tuple[AuditAttachmentKind, str | None]:
    """Resolve audit attachment kind and attached target name.

    For schema-attached audits, validates the declared attachment is schedulable.
    For singular audits, infers attachment from refs and graph structure.
    Returns (attachment_kind, attached_target_name).
    """

    if audit.attached_target_kind == AttachedAuditTargetKind.SOURCE:
        _validate_source_attached_audit(audit=audit)
        return AuditAttachmentKind.SOURCE, audit.attached_target_name

    if audit.attached_target_kind == AttachedAuditTargetKind.MODEL:
        _validate_model_attached_audit(
            audit=audit,
            upstream_deps=upstream_deps,
        )
        return AuditAttachmentKind.MODEL, audit.attached_target_name

    return _infer_singular_attachment(
        audit=audit,
        upstream_deps=upstream_deps,
        downstream_deps=downstream_deps,
    )


def resolve_effective_run_scope(
    *,
    requested_run_scope: AuditRunScope,
    attached_model_materialization: str | None,
) -> AuditRunScope:
    """Resolve effective run scope after degradation rules.

    delta_and_final degrades to final when the attached model does not expose a delta phase.
    Source and end audits always pass None materialization, so they degrade naturally.
    """

    if requested_run_scope == AuditRunScope.FINAL:
        return AuditRunScope.FINAL

    if attached_model_materialization not in (
        MaterializationType.INCREMENTAL,
        MaterializationType.SNAPSHOT,
    ):
        return AuditRunScope.FINAL

    return AuditRunScope.DELTA_AND_FINAL


def _validate_source_attached_audit(*, audit: CompiledAudit) -> None:
    """Validate that a source-attached audit does not reference models."""

    ref: CompileSqlReference
    for ref in audit.references:
        if ref.ref_kind == SqlReferenceKind.REF:
            raise PlannerInputError(
                f"audit '{audit.name}': source-attached audit must not reference models "
                f"via {SqlReferenceKind.REF.placeholder_call()}; found "
                f"{SqlReferenceKind.REF.example_call(ref.ref_name)}"
            )


def _validate_model_attached_audit(
    *,
    audit: CompiledAudit,
    upstream_deps: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]],
) -> None:
    """Validate that all model refs in a model-attached audit are upstream of the attached model."""

    if audit.attached_target_name is None:
        raise PlannerInputError(
            f"audit '{audit.name}': model-attached audit is missing an attached model name"
        )
    attached_key: CompiledObjectKey = CompiledObjectKey(
        resource_type=CompiledResourceType.MODEL, name=audit.attached_target_name
    )
    attached_upstream: frozenset[CompiledObjectKey] = _expand_upstream(
        key=attached_key, upstream_deps=upstream_deps
    )

    ref: CompileSqlReference
    for ref in audit.references:
        if ref.ref_kind != SqlReferenceKind.REF:
            continue
        if ref.ref_name == audit.attached_target_name:
            continue
        ref_key: CompiledObjectKey = CompiledObjectKey(
            resource_type=CompiledResourceType.MODEL, name=ref.ref_name
        )
        seed_key: CompiledObjectKey = CompiledObjectKey(
            resource_type=CompiledResourceType.SEED, name=ref.ref_name
        )
        if ref_key not in attached_upstream and seed_key not in attached_upstream:
            raise PlannerInputError(
                f"audit '{audit.name}': model-attached audit on '{audit.attached_target_name}' "
                f"references '{ref.ref_name}' which is not upstream of "
                f"'{audit.attached_target_name}'"
            )


def _infer_singular_attachment(
    *,
    audit: CompiledAudit,
    upstream_deps: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]],
    downstream_deps: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]],
) -> tuple[AuditAttachmentKind, str | None]:
    """Infer attachment for a singular audit from its refs and graph structure."""

    model_ref_names: list[str] = [
        ref.ref_name for ref in audit.references if ref.ref_kind == SqlReferenceKind.REF
    ]
    source_ref_names: list[str] = [
        ref.ref_name for ref in audit.references if ref.ref_kind == SqlReferenceKind.SOURCE
    ]

    if not model_ref_names and source_ref_names:
        attached_source: str = sorted(source_ref_names)[0]
        return AuditAttachmentKind.SOURCE, attached_source

    if not model_ref_names and not source_ref_names:
        return AuditAttachmentKind.END, None

    if len(model_ref_names) == 1:
        return AuditAttachmentKind.MODEL, model_ref_names[0]

    latest_owner: str | None = _find_single_safe_latest_owner(
        model_ref_names=model_ref_names,
        downstream_deps=downstream_deps,
    )
    if latest_owner is not None:
        return AuditAttachmentKind.MODEL, latest_owner

    return AuditAttachmentKind.END, None


def _find_single_safe_latest_owner(
    *,
    model_ref_names: list[str],
    downstream_deps: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]],
) -> str | None:
    """Find the single model that all other referenced models can reach transitively."""

    model_keys: list[CompiledObjectKey] = [
        CompiledObjectKey(resource_type=CompiledResourceType.MODEL, name=name)
        for name in model_ref_names
    ]
    model_key_set: frozenset[CompiledObjectKey] = frozenset(model_keys)

    candidates: list[CompiledObjectKey] = []
    candidate: CompiledObjectKey
    for candidate in model_keys:
        all_reach: bool = True
        other: CompiledObjectKey
        for other in model_keys:
            if other == candidate:
                continue
            reachable: frozenset[CompiledObjectKey] = expand_downstream(other, downstream_deps)
            if candidate not in reachable:
                all_reach = False
                break
        if all_reach:
            candidates.append(candidate)

    if len(candidates) == 1:
        return candidates[0].name

    if len(candidates) > 1:
        ordered: list[CompiledObjectKey] = sorted(candidates, key=lambda k: k.name)
        deepest: CompiledObjectKey = ordered[0]
        other_candidate: CompiledObjectKey
        for other_candidate in ordered[1:]:
            reachable_from_deepest: frozenset[CompiledObjectKey] = expand_downstream(
                deepest, downstream_deps
            )
            if other_candidate in reachable_from_deepest:
                deepest = other_candidate
        all_others_reach: bool = True
        check_key: CompiledObjectKey
        for check_key in model_key_set:
            if check_key == deepest:
                continue
            if deepest not in expand_downstream(check_key, downstream_deps):
                all_others_reach = False
                break
        if all_others_reach:
            return deepest.name

    return None


def _expand_upstream(
    *,
    key: CompiledObjectKey,
    upstream_deps: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]],
) -> frozenset[CompiledObjectKey]:
    """Return all transitive upstream keys reachable from the given key."""

    visited: set[CompiledObjectKey] = set()
    stack: list[CompiledObjectKey] = [key]
    while stack:
        current: CompiledObjectKey = stack.pop()
        neighbor: CompiledObjectKey
        for neighbor in upstream_deps.get(current, ()):
            if neighbor in visited:
                continue
            visited.add(neighbor)
            stack.append(neighbor)
    return frozenset(visited)
