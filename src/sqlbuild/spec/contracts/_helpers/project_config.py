"""Project configuration resolution implementations."""

from __future__ import annotations

from sqlbuild.spec.contracts.models import (
    LocalConfig,
    ProjectConfig,
    ScenarioConfig,
    ScenarioSnapshotLimitsConfig,
)


def resolve_effective_adapter_name(
    *, project_config: ProjectConfig, local_config: LocalConfig
) -> str:
    """Resolve the effective adapter name, allowing local override."""

    if local_config.adapter is not None:
        return local_config.adapter
    return project_config.adapter


def resolve_effective_scenario_config(
    *, project_config: ProjectConfig, local_config: LocalConfig
) -> ScenarioConfig:
    """Resolve scenario config, allowing local overrides to replace project rules."""

    local_type_overrides: dict[str, dict[str, str]] = {
        dialect: dict(rules)
        for dialect, rules in project_config.scenario.local_type_overrides.items()
    }
    dialect: str
    rules: dict[str, str]
    for dialect, rules in local_config.scenario.local_type_overrides.items():
        local_type_overrides.setdefault(dialect, {}).update(rules)
    project_limits: ScenarioSnapshotLimitsConfig = project_config.scenario.snapshot_limits
    local_limits: ScenarioSnapshotLimitsConfig = local_config.scenario.snapshot_limits
    return ScenarioConfig(
        local_type_overrides=local_type_overrides,
        snapshot_limits=ScenarioSnapshotLimitsConfig(
            max_rows_per_relation=_resolve_optional_int_override(
                project_value=project_limits.max_rows_per_relation,
                local_value=local_limits.max_rows_per_relation,
            ),
            max_total_rows=_resolve_optional_int_override(
                project_value=project_limits.max_total_rows,
                local_value=local_limits.max_total_rows,
            ),
            max_bytes_per_relation=_resolve_optional_int_override(
                project_value=project_limits.max_bytes_per_relation,
                local_value=local_limits.max_bytes_per_relation,
            ),
            max_total_bytes=_resolve_optional_int_override(
                project_value=project_limits.max_total_bytes,
                local_value=local_limits.max_total_bytes,
            ),
        ),
    )


def scenario_local_type_overrides_for_dialect(
    *, scenario_config: ScenarioConfig, sql_analysis_dialect: str | None
) -> dict[str, str]:
    """Return global and dialect-specific scenario local type override rules."""

    overrides: dict[str, str] = dict(scenario_config.local_type_overrides.get("*", {}))
    if sql_analysis_dialect is not None:
        overrides.update(scenario_config.local_type_overrides.get(sql_analysis_dialect, {}))
    return overrides


def _resolve_optional_int_override(
    *, project_value: int | None, local_value: int | None
) -> int | None:
    return local_value if local_value is not None else project_value
