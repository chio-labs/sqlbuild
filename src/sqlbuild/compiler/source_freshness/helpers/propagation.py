"""Direct source freshness downstream propagation helpers."""

from __future__ import annotations

from sqlbuild.compiler.compile.models.core import CompiledObjectKey
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.planner.models import PlannerScope
from sqlbuild.compiler.source_freshness.models import (
    DirectSourceFreshnessPlanningResult,
    DirectSourceFreshnessPropagationResult,
    SourceFreshnessIdentity,
)


def build_direct_source_freshness_propagation_result(
    *,
    source_freshness: DirectSourceFreshnessPlanningResult,
    scope: PlannerScope,
) -> DirectSourceFreshnessPropagationResult:
    """Map changed/unknown source freshness roots to downstream model names."""

    changed_source_model_names: dict[SourceFreshnessIdentity, frozenset[str]] = {}
    unknown_source_model_names: dict[str, frozenset[str]] = {}
    stale_model_names: set[str] = set()

    identity: SourceFreshnessIdentity
    for identity in source_freshness.changed_identities:
        model_names: frozenset[str] = _downstream_model_names(
            source_name=identity.source_name,
            scope=scope,
        )
        changed_source_model_names[identity] = model_names
        stale_model_names.update(model_names)

    source_name: str
    for source_name in source_freshness.unknown_source_names:
        model_names = _downstream_model_names(source_name=source_name, scope=scope)
        unknown_source_model_names[source_name] = model_names
        stale_model_names.update(model_names)

    return DirectSourceFreshnessPropagationResult(
        changed_source_model_names=changed_source_model_names,
        unknown_source_model_names=unknown_source_model_names,
        stale_model_names=frozenset(stale_model_names),
    )


def _downstream_model_names(*, source_name: str, scope: PlannerScope) -> frozenset[str]:
    source_key: CompiledObjectKey = CompiledObjectKey(
        resource_type=CompiledResourceType.SOURCE,
        name=source_name,
    )
    downstream_keys: frozenset[CompiledObjectKey] = _expand_downstream(
        source_key,
        scope.downstream_deps,
    )
    return frozenset(
        key.name for key in downstream_keys if key.resource_type == CompiledResourceType.MODEL
    )


def _expand_downstream(
    key: CompiledObjectKey,
    downstream: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]],
) -> frozenset[CompiledObjectKey]:
    visited: set[CompiledObjectKey] = set()
    stack: list[CompiledObjectKey] = [key]
    while stack:
        current: CompiledObjectKey = stack.pop()
        neighbor: CompiledObjectKey
        for neighbor in downstream.get(current, ()):
            if neighbor in visited:
                continue
            visited.add(neighbor)
            stack.append(neighbor)
    return frozenset(visited)
