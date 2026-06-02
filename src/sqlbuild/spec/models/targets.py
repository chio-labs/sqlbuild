"""Target config resolution helpers."""

from __future__ import annotations

from sqlbuild.spec.models.exceptions import SpecConfigError
from sqlbuild.spec.models.project import (
    ClonePolicy,
    LocalClonePolicy,
    LocalConfig,
    LocalStateConfig,
    LocalTargetConfig,
    ProjectConfig,
    StateConfig,
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
    return TargetConfig(
        connection={**project_target.connection, **local_target.connection},
        vars={**project_target.vars, **local_target.vars},
        database=(
            local_target.database if local_target.database is not None else project_target.database
        ),
        schema=local_target.schema if local_target.schema is not None else project_target.schema,
        defer_sources_to=(
            local_target.defer_sources_to
            if local_target.defer_sources_to is not None
            else project_target.defer_sources_to
        ),
        clone=_merge_clone_policy(
            project_clone=project_target.clone,
            local_clone=local_target.clone,
        ),
        state=_merge_state_config(
            project_state=project_target.state,
            local_state=local_target.state,
        ),
    )


def _merge_clone_policy(
    *, project_clone: ClonePolicy, local_clone: LocalClonePolicy
) -> ClonePolicy:
    allow_as_source: bool | None = local_clone.allow_as_source
    allow_as_target: bool | None = local_clone.allow_as_target
    return ClonePolicy(
        allow_as_source=(
            allow_as_source if allow_as_source is not None else project_clone.allow_as_source
        ),
        allow_as_target=(
            allow_as_target if allow_as_target is not None else project_clone.allow_as_target
        ),
    )


def _merge_state_config(
    *,
    project_state: StateConfig,
    local_state: LocalStateConfig,
) -> StateConfig:
    return StateConfig(
        backend=local_state.backend if local_state.backend is not None else project_state.backend,
        schema=local_state.schema if local_state.schema is not None else project_state.schema,
        connection={**project_state.connection, **local_state.connection},
        allow_reset=(
            local_state.allow_reset
            if local_state.allow_reset is not None
            else project_state.allow_reset
        ),
        unsuffixed_virtual_env=(
            local_state.unsuffixed_virtual_env
            if local_state.unsuffixed_virtual_env is not None
            else project_state.unsuffixed_virtual_env
        ),
    )
