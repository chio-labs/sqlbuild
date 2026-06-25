"""Planner helpers for dependency baseline preparation."""

from __future__ import annotations

from dataclasses import replace

from sqlbuild.compiler.compile.models.core import CompiledModel, CompiledObjectKey
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.fingerprints.models import Fingerprint
from sqlbuild.compiler.planner.models import (
    DependencyBaselinePlanEntry,
    ExistingDestinationInputPlanEntry,
    ModelPlanEntry,
    PlannerScope,
)


def build_dependency_baseline_candidate_keys(scope: PlannerScope) -> frozenset[CompiledObjectKey]:
    """Return direct unselected SQL model dependencies that can be baseline-prepared."""

    candidates: set[CompiledObjectKey] = set()
    selected_key: CompiledObjectKey
    for selected_key in scope.selected_keys:
        dep_key: CompiledObjectKey
        for dep_key in scope.upstream_deps.get(selected_key, ()):
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

    baseline_entries: list[DependencyBaselinePlanEntry] = []
    for entry in entries:
        if entry.key not in candidate_keys or entry.relation_reuse is None:
            continue
        baseline_entries.append(
            DependencyBaselinePlanEntry(
                name=entry.name,
                destination=entry.destination,
                relation_reuse=entry.relation_reuse,
                fingerprint_version_hash=entry.fingerprint_version_hash,
                resource_label=entry.materialization_type.value,
            )
        )
    return tuple(baseline_entries)


def build_existing_destination_input_entries(
    *,
    scope: PlannerScope,
    candidate_keys: frozenset[CompiledObjectKey],
    reusable_keys: frozenset[CompiledObjectKey],
    existing_relation_names: frozenset[str],
    expected_version_hashes: dict[str, str],
    destination_fingerprints: dict[str, Fingerprint],
) -> tuple[ExistingDestinationInputPlanEntry, ...]:
    """Return non-reused direct inputs that already exist in the destination target."""

    entries: list[ExistingDestinationInputPlanEntry] = []
    key: CompiledObjectKey
    for key in sorted(candidate_keys - reusable_keys, key=lambda item: item.name):
        if key.name not in existing_relation_names:
            continue
        model: CompiledModel | None = scope.models_by_name.get(key.name)
        if model is None:
            continue
        expected_version_hash: str | None = expected_version_hashes.get(key.name)
        destination_version_hash: str | None = (
            destination_fingerprints[key.name].version_hash
            if key.name in destination_fingerprints
            else None
        )
        entries.append(
            ExistingDestinationInputPlanEntry(
                name=key.name,
                destination=model.destination,
                status=(
                    "current"
                    if expected_version_hash is not None
                    and destination_version_hash == expected_version_hash
                    else "stale"
                ),
                expected_version_hash=expected_version_hash,
                destination_version_hash=destination_version_hash,
            )
        )
    return tuple(entries)
