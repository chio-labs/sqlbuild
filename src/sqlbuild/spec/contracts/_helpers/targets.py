"""Target selection and target merging, resolved natively over the loaded config objects."""

from __future__ import annotations

from typing import Any

import sqlbuild._native as _native
from sqlbuild.spec.contracts.exceptions import SpecConfigError
from sqlbuild.spec.contracts.models import (
    ClonePolicy,
    ExecutionLimitsConfig,
    LocalConfig,
    ProjectConfig,
    TargetConfig,
    TargetDiffConfig,
    TargetWarehousesConfig,
)

_GROUPS: dict[str, type[object]] = {
    "clone": ClonePolicy,
    "execution_limits": ExecutionLimitsConfig,
    "diff": TargetDiffConfig,
    "warehouses": TargetWarehousesConfig,
}


def resolve_target_name(
    *,
    project_config: ProjectConfig,
    local_config: LocalConfig,
    selected_target: str | None,
) -> str | None:
    """Resolve the effective target name."""

    name, error = _native.effective_config_target_name(
        project_config, local_config, selected_target
    )
    if error is not None:
        raise SpecConfigError(error)
    return name


def resolve_target_config(
    *,
    project_config: ProjectConfig,
    local_config: LocalConfig,
    target_name: str,
) -> TargetConfig:
    """Merge project target config with local developer overrides."""

    rows, error = _native.effective_config_target_fields(
        (project_config, local_config), target_name, TargetConfig()
    )
    if rows is None:
        raise SpecConfigError(error or "")
    values: dict[str, Any] = {}
    grouped: dict[str, dict[str, Any]] = {group: {} for group in _GROUPS}
    for group, name, value in rows:
        (values if group is None else grouped[group])[name] = value
    nested: dict[str, Any] = {group: kind(**grouped[group]) for group, kind in _GROUPS.items()}
    return TargetConfig(**values, **nested)
