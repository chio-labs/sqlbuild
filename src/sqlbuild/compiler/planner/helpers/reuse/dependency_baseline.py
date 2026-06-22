"""Planner helpers for dependency baseline preparation."""

from __future__ import annotations

from dataclasses import replace

from sqlbuild.compiler.compile.models.core import CompiledObjectKey
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.planner.models import (
    DependencyBaselinePlanEntry,
    ModelPlanEntry,
    PlannerScope,
)


def build_dependency_baseline_candidate_keys(scope: PlannerScope) -> frozenset[CompiledObjectKey]:
    """Return direct unselected SQL model dependencies that can be baseline-prepared."""

    candidates: set[CompiledObjectKey] = set()
    selected_key: CompiledObjectKey
    for selected_key in scope.selected_keys:
        dep_key: CompiledObjectKey
        for dep_key in scope.upstream_deps.get(selected_key, ()):  # direct physical inputs only
            if dep_key in scope.selected_keys:
                continue
            if dep_key.resource_type != CompiledResourceType.MODEL:
                continue
            candidates.add(dep_key)
    return frozenset(candidates)


def with_dependency_baseline_candidates(
    *, scope: PlannerScope, candidate_keys: frozenset[CompiledObjectKey]
) -> PlannerScope:
    """Return planning scope extended with baseline candidates for state inspection only."""

    if not candidate_keys:
        return scope
    return replace(scope, selected_keys=scope.selected_keys | candidate_keys)


def build_dependency_baseline_entries(
    *,
    entries: tuple[ModelPlanEntry, ...],
    candidate_keys: frozenset[CompiledObjectKey],
) -> tuple[DependencyBaselinePlanEntry, ...]:
    """Build generic baseline entries from reusable model plan entries."""

    return tuple(
        DependencyBaselinePlanEntry(
            name=entry.name,
            destination=entry.destination,
            relation_reuse=entry.relation_reuse,
            fingerprint_version_hash=entry.fingerprint_version_hash,
            resource_label=entry.materialization_type.value,
        )
        for entry in entries
        if entry.key in candidate_keys and entry.relation_reuse is not None
    )
