"""Environment config resolution helpers."""

from __future__ import annotations

from sqlbuild.spec.models.exceptions import SpecConfigError
from sqlbuild.spec.models.project import (
    ClonePolicy,
    EnvironmentConfig,
    LocalClonePolicy,
    LocalConfig,
    LocalEnvironmentConfig,
    LocalStateConfig,
    ProjectConfig,
    StateConfig,
)


def resolve_environment_name(
    *,
    project_config: ProjectConfig,
    local_config: LocalConfig,
    selected_environment: str | None,
) -> str | None:
    """Resolve the effective environment name."""

    environment_name: str | None = selected_environment
    if environment_name is None:
        environment_name = local_config.environment
    if environment_name is None:
        environment_name = project_config.default_environment
    if environment_name is None:
        return None
    if (
        environment_name not in project_config.environments
        and environment_name not in local_config.environments
    ):
        raise SpecConfigError(f"Unknown environment '{environment_name}'")
    return environment_name


def resolve_environment_config(
    *,
    project_config: ProjectConfig,
    local_config: LocalConfig,
    environment_name: str,
) -> EnvironmentConfig:
    """Merge project environment config with local developer overrides."""

    project_environment: EnvironmentConfig = project_config.environments.get(
        environment_name, EnvironmentConfig()
    )
    local_environment: LocalEnvironmentConfig | None = local_config.environments.get(
        environment_name
    )
    if local_environment is None:
        return project_environment
    return EnvironmentConfig(
        connection={**project_environment.connection, **local_environment.connection},
        vars={**project_environment.vars, **local_environment.vars},
        database=(
            local_environment.database
            if local_environment.database is not None
            else project_environment.database
        ),
        schema=(
            local_environment.schema
            if local_environment.schema is not None
            else project_environment.schema
        ),
        defer_sources_to=(
            local_environment.defer_sources_to
            if local_environment.defer_sources_to is not None
            else project_environment.defer_sources_to
        ),
        clone=_merge_clone_policy(
            project_clone=project_environment.clone,
            local_clone=local_environment.clone,
        ),
        state=_merge_state_config(
            project_state=project_environment.state,
            local_state=local_environment.state,
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
