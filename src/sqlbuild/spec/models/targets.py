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
        _validate_reuse_config(
            target_name=target_name,
            target_config=project_target,
            project_config=project_config,
            local_config=local_config,
        )
        return project_target
    target_config: TargetConfig = TargetConfig(
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
        reuse_from=(
            local_target.reuse_from
            if local_target.reuse_from is not None
            else project_target.reuse_from
        ),
        reuse_strict=(
            local_target.reuse_strict
            if local_target.reuse_strict is not None
            else project_target.reuse_strict
        ),
        trust_reuse_inputs=(
            local_target.trust_reuse_inputs
            if local_target.trust_reuse_inputs is not None
            else project_target.trust_reuse_inputs
        ),
        force=local_target.force if local_target.force is not None else project_target.force,
        reuse_hard_copy=(
            local_target.reuse_hard_copy
            if local_target.reuse_hard_copy is not None
            else project_target.reuse_hard_copy
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
    _validate_reuse_config(
        target_name=target_name,
        target_config=target_config,
        project_config=project_config,
        local_config=local_config,
    )
    return target_config


def resolve_effective_force(
    *,
    project_config: ProjectConfig,
    local_config: LocalConfig,
    selected_target: str | None,
    cli_force: bool,
) -> bool:
    """Resolve configured force with CLI, target, and settings precedence."""

    if cli_force:
        return True
    target_name: str | None = resolve_target_name(
        project_config=project_config,
        local_config=local_config,
        selected_target=selected_target,
    )
    if target_name is not None:
        target_config: TargetConfig = resolve_target_config(
            project_config=project_config,
            local_config=local_config,
            target_name=target_name,
        )
        if target_config.force is not None:
            return target_config.force
    return (
        local_config.settings.force
        if "force" in local_config.setting_overrides
        else project_config.settings.force
    )


def _validate_reuse_config(
    *,
    target_name: str,
    target_config: TargetConfig,
    project_config: ProjectConfig,
    local_config: LocalConfig,
) -> None:
    reuse_from: str | None = target_config.reuse_from
    if reuse_from is None:
        return
    if reuse_from == target_name:
        raise SpecConfigError(f"Target '{target_name}' cannot reuse from itself")
    known_targets: set[str] = set(project_config.targets) | set(local_config.targets)
    if reuse_from not in known_targets:
        raise SpecConfigError(
            f"Target '{target_name}' reuse_from references unknown target '{reuse_from}'"
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
