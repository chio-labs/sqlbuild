"""Target configuration resolution implementations."""

from __future__ import annotations

from sqlbuild.spec.contracts.exceptions import SpecConfigError
from sqlbuild.spec.contracts.models import (
    ClonePolicy,
    ExecutionLimitsConfig,
    LocalClonePolicy,
    LocalConfig,
    LocalTargetConfig,
    ProjectConfig,
    TargetConfig,
)


def resolve_target_name(
    *,
    project_config: ProjectConfig,
    local_config: LocalConfig,
    selected_target: str | None,
) -> str | None:
    """Resolve the effective target name."""

    target_name: str | None = selected_target
    if target_name is None:
        target_name = local_config.target
    if target_name is None:
        target_name = project_config.default_target
    if target_name is None:
        return None
    if target_name not in project_config.targets and target_name not in local_config.targets:
        raise SpecConfigError(f"Unknown target '{target_name}'")
    return target_name


def resolve_target_config(
    *,
    project_config: ProjectConfig,
    local_config: LocalConfig,
    target_name: str,
) -> TargetConfig:
    """Merge project target config with local developer overrides."""

    project_target: TargetConfig = project_config.targets.get(target_name, TargetConfig())
    local_target: LocalTargetConfig | None = local_config.targets.get(target_name)
    if local_target is None:
        return project_target
    local_overrides_retention: bool = (
        local_target.time_travel_retention is not None
        or local_target.time_travel_retention_by_materialization is not None
    )
    target_config: TargetConfig = TargetConfig(
        connection={**project_target.connection, **local_target.connection},
        connection_name=(
            local_target.connection_name
            if local_target.connection_name is not None
            else project_target.connection_name
        ),
        vars={**project_target.vars, **local_target.vars},
        database=(
            local_target.database if local_target.database is not None else project_target.database
        ),
        schema=local_target.schema if local_target.schema is not None else project_target.schema,
        loader_schema=(
            local_target.loader_schema
            if local_target.loader_schema is not None
            else project_target.loader_schema
        ),
        defer_sources_to=(
            local_target.defer_sources_to
            if local_target.defer_sources_to is not None
            else project_target.defer_sources_to
        ),
        defer_clone_from=(
            local_target.defer_clone_from
            if local_target.defer_clone_from is not None
            else project_target.defer_clone_from
        ),
        compile_cache=(
            local_target.compile_cache
            if local_target.compile_cache is not None
            else project_target.compile_cache
        ),
        time_travel_retention=(
            local_target.time_travel_retention
            if local_overrides_retention
            else project_target.time_travel_retention
        ),
        time_travel_retention_by_materialization=(
            local_target.time_travel_retention_by_materialization or {}
            if local_overrides_retention
            else project_target.time_travel_retention_by_materialization
        ),
        owns_time_travel_retention_namespace=(
            local_target.owns_time_travel_retention_namespace
            if local_target.owns_time_travel_retention_namespace is not None
            else project_target.owns_time_travel_retention_namespace
        ),
        default_table_type=(
            local_target.default_table_type
            if local_target.default_table_type is not None
            else project_target.default_table_type
        ),
        table_type_downgrade=(
            local_target.table_type_downgrade
            if local_target.table_type_downgrade is not None
            else project_target.table_type_downgrade
        ),
        time_travel_retention_decrease=(
            local_target.time_travel_retention_decrease
            if local_target.time_travel_retention_decrease is not None
            else project_target.time_travel_retention_decrease
        ),
        execution_limits=_merge_execution_limits(
            project_limits=project_target.execution_limits,
            local_limits=local_target.execution_limits,
        ),
        clone=_merge_clone_policy(
            project_clone=project_target.clone,
            local_clone=local_target.clone,
        ),
    )
    return target_config


def _merge_execution_limits(
    *, project_limits: ExecutionLimitsConfig, local_limits: ExecutionLimitsConfig
) -> ExecutionLimitsConfig:
    return ExecutionLimitsConfig(
        max_models=(
            local_limits.max_models
            if local_limits.max_models is not None
            else project_limits.max_models
        ),
        max_duration=(
            local_limits.max_duration
            if local_limits.max_duration is not None
            else project_limits.max_duration
        ),
        max_duration_seconds=(
            local_limits.max_duration_seconds
            if local_limits.max_duration is not None
            else project_limits.max_duration_seconds
        ),
        remediation=(
            local_limits.remediation
            if local_limits.remediation is not None
            else project_limits.remediation
        ),
    )


def _merge_clone_policy(
    *, project_clone: ClonePolicy, local_clone: LocalClonePolicy
) -> ClonePolicy:
    allow_as_clone_origin: bool | None = local_clone.allow_as_clone_origin
    allow_as_clone_destination: bool | None = local_clone.allow_as_clone_destination
    return ClonePolicy(
        allow_as_clone_origin=(
            allow_as_clone_origin
            if allow_as_clone_origin is not None
            else project_clone.allow_as_clone_origin
        ),
        allow_as_clone_destination=(
            allow_as_clone_destination
            if allow_as_clone_destination is not None
            else project_clone.allow_as_clone_destination
        ),
    )
