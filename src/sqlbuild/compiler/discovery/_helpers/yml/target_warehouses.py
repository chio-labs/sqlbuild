"""Loading and adapter validation for per-target command-group warehouses."""

from __future__ import annotations

from pathlib import Path
from typing import cast

from sqlbuild.adapter.discovery.main.session_warehouse_support import (
    adapter_supports_session_warehouse,
)
from sqlbuild.compiler.discovery._helpers.validation.supported_keys import (
    reject_unknown_mapping_keys,
)
from sqlbuild.compiler.discovery.constants import LOCAL_CONFIG_FILENAME, PROJECT_CONFIG_FILENAME
from sqlbuild.compiler.discovery.exceptions import ProjectConfigError
from sqlbuild.errors.setting_help.main.setting_note import setting_note
from sqlbuild.spec.contracts.main.resolve_effective_adapter_name import (
    resolve_effective_adapter_name,
)
from sqlbuild.spec.contracts.models import LocalConfig, ProjectConfig, TargetWarehousesConfig
from sqlbuild.spec.contracts.types import WarehouseGroup


def load_target_warehouses(
    *, payload: object, target_name: str, file_path: Path
) -> TargetWarehousesConfig:
    """Parse one target's optional `[targets.<name>.warehouses]` section."""

    label: str = f"targets.{target_name}.warehouses"
    if payload is None:
        return TargetWarehousesConfig()
    if not isinstance(payload, dict):
        raise ProjectConfigError(f"{file_path} {label} must be a mapping")
    mapping: dict[str, object] = cast(dict[str, object], payload)
    reject_unknown_mapping_keys(
        mapping=mapping,
        allowed=frozenset(group.value for group in WarehouseGroup),
        file_path=file_path,
        label=label,
        error_class=ProjectConfigError,
    )
    values: dict[WarehouseGroup, str | None] = {}
    group: WarehouseGroup
    for group in WarehouseGroup:
        value: object | None = mapping.get(group.value)
        if value is not None and (not isinstance(value, str) or not value.strip()):
            raise ProjectConfigError(
                f"{file_path} {label}.{group.value} must be a non-empty warehouse name"
            )
        values[group] = value.strip() if isinstance(value, str) else None
    return TargetWarehousesConfig(
        build=values[WarehouseGroup.BUILD], query=values[WarehouseGroup.QUERY]
    )


def reject_unsupported_target_warehouses(
    *,
    project_dir: Path,
    project_config: ProjectConfig,
    local_config: LocalConfig,
    project_config_path: Path,
    local_config_path: Path,
) -> None:
    """Check shared groups against the shared adapter and local groups against the effective one."""

    project_group: tuple[str, WarehouseGroup, str] | None = _first_configured_group(
        {name: target.warehouses for name, target in project_config.targets.items()}
    )
    if project_group is not None and not adapter_supports_session_warehouse(
        adapter_name=project_config.adapter, project_dir=project_dir
    ):
        _raise_unsupported_target_warehouse(
            adapter_name=project_config.adapter,
            file_path=project_config_path,
            file_name=PROJECT_CONFIG_FILENAME,
            configured=project_group,
        )
    local_group: tuple[str, WarehouseGroup, str] | None = _first_configured_group(
        {name: target.warehouses for name, target in local_config.targets.items()}
    )
    if local_group is None:
        return
    effective_adapter: str = resolve_effective_adapter_name(
        project_config=project_config, local_config=local_config
    )
    if not adapter_supports_session_warehouse(
        adapter_name=effective_adapter, project_dir=project_dir
    ):
        _raise_unsupported_target_warehouse(
            adapter_name=effective_adapter,
            file_path=local_config_path,
            file_name=LOCAL_CONFIG_FILENAME,
            configured=local_group,
        )


def _first_configured_group(
    warehouses_by_target: dict[str, TargetWarehousesConfig],
) -> tuple[str, WarehouseGroup, str] | None:
    target_name: str
    warehouses: TargetWarehousesConfig
    for target_name, warehouses in sorted(warehouses_by_target.items()):
        group: WarehouseGroup
        for group in WarehouseGroup:
            value: str | None = warehouses.for_group(group)
            if value is not None:
                return target_name, group, value
    return None


def _raise_unsupported_target_warehouse(
    *,
    adapter_name: str,
    file_path: Path,
    file_name: str,
    configured: tuple[str, WarehouseGroup, str],
) -> None:
    target_name, group, value = configured
    section: str = f"targets.{target_name}.warehouses"
    raise ProjectConfigError(
        f"{file_path} [{section}] selects a {group.value} warehouse, but the "
        f"'{adapter_name}' adapter has no warehouse to select; "
        + setting_note(file_name=file_name, section=section, key=group.value, value=value),
        help=(
            f"remove the [{section}] section from {file_name}; command-group warehouses need an "
            "adapter with a session warehouse, such as snowflake or an adapter extending it"
        ),
    )
