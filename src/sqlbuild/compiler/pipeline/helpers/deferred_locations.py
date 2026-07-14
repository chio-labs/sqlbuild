"""Compute deferred relation locations and gather deferred relations."""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any

from sqlbuild.adapter.classes.base_adapter import BaseAdapter
from sqlbuild.adapter.models import RelationInfo
from sqlbuild.compiler.compile.constants import PRESERVE_TARGET_VALUE
from sqlbuild.compiler.compile.main.project_var_values import render_project_var_text
from sqlbuild.compiler.compile.models.core import (
    CompiledModel,
    CompiledProject,
    CompiledRelationLocation,
    CompiledSeed,
)
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.compiler.pipeline.constants import DEFERRED_TARGET_CONTEXT_KEYS
from sqlbuild.compiler.planner.exceptions import PlannerInputError
from sqlbuild.spec.contracts.models import TargetConfig

_CTX_PATTERN: re.Pattern[str] = re.compile(r"\$\{CTX:([^}]+)\}")
_VAR_PATTERN: re.Pattern[str] = re.compile(r"\$\{([^}:]+)\}")


def build_deferred_locations(
    *,
    project: CompiledProject,
    deferred_target_config: TargetConfig,
    effective_vars: dict[str, object],
    default_schema: str | None,
    default_database: str | None,
    render_qualified_name: Callable[..., str | None],
) -> dict[str, CompiledRelationLocation]:
    """Build physical locations for all models and seeds under a deferred target."""

    locations: dict[str, CompiledRelationLocation] = {}
    model: CompiledModel
    for model in project.models:
        locations[model.name] = _resolve_deferred_location(
            target=model.destination,
            deferred_target_config=deferred_target_config,
            effective_vars=effective_vars,
            default_schema=default_schema,
            default_database=default_database,
            render_qualified_name=render_qualified_name,
        )
    seed: CompiledSeed
    for seed in project.seeds:
        locations[seed.name] = _resolve_deferred_location(
            target=seed.destination,
            deferred_target_config=deferred_target_config,
            effective_vars=effective_vars,
            default_schema=default_schema,
            default_database=default_database,
            render_qualified_name=render_qualified_name,
        )
    return locations


def resolve_deferred_target_config(
    *,
    discovered_inputs: DiscoveredProjectInputs,
    defer_to: str,
    current_target_name: str | None,
) -> TargetConfig:
    """Validate and resolve the deferred target config."""

    targets: dict[str, TargetConfig] = discovered_inputs.project_config.targets
    if defer_to not in targets:
        raise PlannerInputError(f"Unknown deferred target '{defer_to}'")
    if defer_to == current_target_name:
        raise PlannerInputError(f"Cannot defer to the current target '{defer_to}'")
    return targets[defer_to]


def gather_deferred_relations(
    *,
    adapter: BaseAdapter,
    connection: Any,
    deferred_locations: dict[str, CompiledRelationLocation],
) -> dict[str, RelationInfo]:
    """Gather existing relations from the deferred target's relation-location schemas."""

    schemas: set[str] = set()
    database: str | None = None
    location: CompiledRelationLocation
    for location in deferred_locations.values():
        if location.schema is not None:
            schemas.add(location.schema)
        if location.database is not None and database is None:
            database = location.database

    if not schemas:
        return {}

    relations: tuple[RelationInfo, ...] = adapter.list_relations(
        connection=connection, database=database, schemas=tuple(sorted(schemas))
    )
    return {rel.name: rel for rel in relations}


def _resolve_deferred_location(
    *,
    target: CompiledRelationLocation,
    deferred_target_config: TargetConfig,
    effective_vars: dict[str, object],
    default_schema: str | None,
    default_database: str | None,
    render_qualified_name: Callable[..., str | None],
) -> CompiledRelationLocation:
    """Resolve one relation location under the deferred target's naming rules."""

    schema: str | None = _resolve_target_field(
        target_value=deferred_target_config.schema,
        logical_value=target.logical_schema,
        effective_vars=effective_vars,
    )
    database: str | None = _resolve_target_field(
        target_value=deferred_target_config.database,
        logical_value=target.logical_database,
        effective_vars=effective_vars,
    )

    if schema is None:
        schema = default_schema
    if database is None:
        database = default_database

    qualified_name: str | None = render_qualified_name(
        database=database,
        schema=schema,
        name=target.name,
    )
    return CompiledRelationLocation(
        database=database,
        schema=schema,
        name=target.name,
        qualified_name=qualified_name,
        logical_schema=target.logical_schema,
        logical_database=target.logical_database,
    )


def _resolve_target_field(
    *,
    target_value: str | None,
    logical_value: str | None,
    effective_vars: dict[str, object],
) -> str | None:
    """Resolve one target schema or database field against the logical value."""

    if target_value is None or target_value == PRESERVE_TARGET_VALUE:
        return logical_value

    result: str = target_value

    def _replace_ctx(match: re.Match[str]) -> str:
        ctx_key: str = match.group(1)
        if ctx_key in DEFERRED_TARGET_CONTEXT_KEYS:
            return logical_value if logical_value is not None else ""
        return match.group(0)

    result = _CTX_PATTERN.sub(_replace_ctx, result)

    def _replace_var(match: re.Match[str]) -> str:
        var_name: str = match.group(1)
        if var_name not in effective_vars:
            return match.group(0)
        return render_project_var_text(
            value=effective_vars[var_name],
            label=f"deferred target variable '${{{var_name}}}'",
        )

    result = _VAR_PATTERN.sub(_replace_var, result)

    return result
