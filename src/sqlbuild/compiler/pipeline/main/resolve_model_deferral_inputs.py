"""Resolve native SQLBuild model deferral inputs."""

from __future__ import annotations

from typing import Any

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.adapter.contract.models import RelationInfo
from sqlbuild.compiler.compile.models import CompiledProject, CompiledRelationLocation
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.compiler.pipeline._helpers.deferred_locations import (
    build_deferred_locations,
    gather_deferred_relations,
    resolve_deferred_target_config,
)
from sqlbuild.compiler.planner.models import DeferralInputs
from sqlbuild.spec.contracts.models import TargetConfig


def resolve_model_deferral_inputs(
    *,
    project: CompiledProject,
    discovered_inputs: DiscoveredProjectInputs,
    adapter: BaseAdapter,
    connection: Any,
    defer_to: str | None,
) -> DeferralInputs:
    """Resolve native target locations and warehouse relations for model deferral."""

    if defer_to is None:
        return DeferralInputs()
    deferred_target_config: TargetConfig = resolve_deferred_target_config(
        discovered_inputs=discovered_inputs,
        defer_to=defer_to,
        current_target_name=project.effective_target_name,
    )
    deferred_locations: dict[str, CompiledRelationLocation] = build_deferred_locations(
        project=project,
        deferred_target_config=deferred_target_config,
        effective_vars=project.effective_vars,
        default_schema=adapter.default_schema(),
        default_database=adapter.default_database(),
        render_qualified_name=adapter.render_qualified_name,
    )
    deferred_relations: dict[str, RelationInfo] = gather_deferred_relations(
        adapter=adapter,
        connection=connection,
        deferred_locations=deferred_locations,
    )
    return DeferralInputs(
        deferred_locations=deferred_locations,
        deferred_relations=deferred_relations,
    )
