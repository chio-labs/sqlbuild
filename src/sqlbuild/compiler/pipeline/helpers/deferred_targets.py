"""Compute deferred environment targets and gather deferred relations."""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.adapter.shared.models import RelationInfo
from sqlbuild.compiler.compile.constants import PRESERVE_ENVIRONMENT_VALUE
from sqlbuild.compiler.compile.models.core import (
    CompiledModel,
    CompiledProject,
    CompiledRelationTarget,
    CompiledSeed,
)
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.shared.helpers.project_var_values import render_project_var_text
from sqlbuild.spec.models.project import EnvironmentConfig

_CTX_PATTERN: re.Pattern[str] = re.compile(r"\$\{CTX:([^}]+)\}")
_VAR_PATTERN: re.Pattern[str] = re.compile(r"\$\{([^}:]+)\}")


def build_deferred_targets(
    *,
    project: CompiledProject,
    deferred_env: EnvironmentConfig,
    effective_vars: dict[str, object],
    default_schema: str | None,
    default_database: str | None,
    render_qualified_name: Callable[..., str | None],
) -> dict[str, CompiledRelationTarget]:
    """Build physical targets for all models and seeds under a deferred environment."""

    targets: dict[str, CompiledRelationTarget] = {}
    model: CompiledModel
    for model in project.models:
        targets[model.name] = _resolve_deferred_target(
            target=model.target,
            deferred_env=deferred_env,
            effective_vars=effective_vars,
            default_schema=default_schema,
            default_database=default_database,
            render_qualified_name=render_qualified_name,
        )
    seed: CompiledSeed
    for seed in project.seeds:
        targets[seed.name] = _resolve_deferred_target(
            target=seed.target,
            deferred_env=deferred_env,
            effective_vars=effective_vars,
            default_schema=default_schema,
            default_database=default_database,
            render_qualified_name=render_qualified_name,
        )
    return targets


def resolve_deferred_env(
    *,
    discovered_inputs: DiscoveredProjectInputs,
    defer_to: str,
    current_env_name: str | None,
) -> EnvironmentConfig:
    """Validate and resolve the deferred environment config."""

    environments: dict[str, EnvironmentConfig] = discovered_inputs.project_config.environments
    if defer_to not in environments:
        raise ValueError(f"Unknown deferred environment '{defer_to}'")
    if defer_to == current_env_name:
        raise ValueError(f"Cannot defer to the current environment '{defer_to}'")
    return environments[defer_to]


def gather_deferred_relations(
    *,
    adapter: BaseAdapter,
    connection: Any,
    deferred_targets: dict[str, CompiledRelationTarget],
) -> dict[str, RelationInfo]:
    """Gather existing relations from the deferred environment's schemas."""

    schemas: set[str] = set()
    database: str | None = None
    target: CompiledRelationTarget
    for target in deferred_targets.values():
        if target.schema is not None:
            schemas.add(target.schema)
        if target.database is not None and database is None:
            database = target.database

    if not schemas:
        return {}

    relations: tuple[RelationInfo, ...] = adapter.list_relations(
        connection, database=database, schemas=tuple(sorted(schemas))
    )
    return {rel.name: rel for rel in relations}


def _resolve_deferred_target(
    *,
    target: CompiledRelationTarget,
    deferred_env: EnvironmentConfig,
    effective_vars: dict[str, object],
    default_schema: str | None,
    default_database: str | None,
    render_qualified_name: Callable[..., str | None],
) -> CompiledRelationTarget:
    """Resolve one target under the deferred environment's naming rules."""

    schema: str | None = _resolve_env_field(
        env_value=deferred_env.schema,
        logical_value=target.logical_schema,
        effective_vars=effective_vars,
    )
    database: str | None = _resolve_env_field(
        env_value=deferred_env.database,
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
    return CompiledRelationTarget(
        database=database,
        schema=schema,
        name=target.name,
        qualified_name=qualified_name,
        logical_schema=target.logical_schema,
        logical_database=target.logical_database,
    )


def _resolve_env_field(
    *,
    env_value: str | None,
    logical_value: str | None,
    effective_vars: dict[str, object],
) -> str | None:
    """Resolve one environment schema or database field against the logical value."""

    if env_value is None or env_value == PRESERVE_ENVIRONMENT_VALUE:
        return logical_value

    result: str = env_value

    def _replace_ctx(match: re.Match[str]) -> str:
        ctx_key: str = match.group(1)
        if ctx_key in ("schema", "database"):
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
