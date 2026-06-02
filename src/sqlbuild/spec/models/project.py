"""Project configuration models."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ClonePolicy:
    """Environment clone policy."""

    allow_as_source: bool = False
    allow_as_target: bool = False


@dataclass(frozen=True)
class LocalClonePolicy:
    """Local environment clone policy overrides."""

    allow_as_source: bool | None = None
    allow_as_target: bool | None = None


@dataclass(frozen=True)
class StateConfig:
    """Virtual mode state store configuration."""

    backend: str | None = None
    schema: str | None = None
    connection: dict[str, object] = field(default_factory=dict)
    allow_reset: bool = False
    unsuffixed_virtual_env: str | None = None


@dataclass(frozen=True)
class LocalStateConfig:
    """Local virtual environment mode state store overrides."""

    backend: str | None = None
    schema: str | None = None
    connection: dict[str, object] = field(default_factory=dict)
    allow_reset: bool | None = None
    unsuffixed_virtual_env: str | None = None


@dataclass(frozen=True)
class TargetConfig:
    """One named target configuration."""

    connection: dict[str, object] = field(default_factory=dict)
    vars: dict[str, str] = field(default_factory=dict)
    database: str | None = None
    schema: str | None = None
    defer_sources_to: str | None = None
    clone: ClonePolicy = field(default_factory=ClonePolicy)
    state: StateConfig = field(default_factory=StateConfig)


@dataclass(frozen=True)
class LocalTargetConfig:
    """Local developer overrides for one named target."""

    connection: dict[str, object] = field(default_factory=dict)
    vars: dict[str, str] = field(default_factory=dict)
    database: str | None = None
    schema: str | None = None
    defer_sources_to: str | None = None
    clone: LocalClonePolicy = field(default_factory=LocalClonePolicy)
    state: LocalStateConfig = field(default_factory=LocalStateConfig)


@dataclass(frozen=True)
class SettingsConfig:
    """Global feature toggles."""

    sqlglot: bool = True
    query_change_tracking: bool = True
    sql_validation: bool = True
    concurrency: int = 1
    auto_load_sources: bool = True
    virtual_environments: bool = False
    table_promotion_mode: str | None = None
    default_audit_severity: str | None = None
    default_audit_run_scope: str | None = None


@dataclass(frozen=True)
class DefaultsConfig:
    """Project-wide model defaults."""

    materialized: str | None = None
    database: str | None = None
    schema: str | None = None
    incremental_strategy: str | None = None
    incremental_mode: str | None = None
    append_cursor_inclusive: object | None = None
    cursor_start: object | None = None
    lookback: str | None = None
    batch_size: str | int | None = None
    query_change_backfill: str | None = None
    schema_change_backfill: dict[str, str] = field(default_factory=dict)
    row_diff_exclude_columns: tuple[str, ...] = field(default_factory=tuple)
    row_diff_tolerances: dict[str, object] = field(default_factory=dict)
    tags: tuple[str, ...] = field(default_factory=tuple)
    contract: str | None = None


@dataclass(frozen=True)
class JanitorConfig:
    """Janitor command defaults."""

    enabled: bool = False
    retention_days: int = 30
    max_checkpoints: int = 20
    delete_tracked_only: bool = True
    exclude_patterns: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class SnapshotsConfig:
    """Snapshot materialization safety defaults."""

    current_state_full_refresh: str = "deny"
    historical_full_refresh: str = "require_confirmation"
    schema_change: str = "append_new_columns"
    wildcard_check_schema_change: str = "require_confirmation"


@dataclass(frozen=True)
class ScenarioSnapshotLimitsConfig:
    """Scenario snapshot capture safety limits."""

    max_rows_per_relation: int | None = None
    max_total_rows: int | None = None
    max_bytes_per_relation: int | None = None
    max_total_bytes: int | None = None


@dataclass(frozen=True)
class ScenarioConfig:
    """Scenario command configuration."""

    local_type_overrides: dict[str, dict[str, str]] = field(default_factory=dict)
    snapshot_limits: ScenarioSnapshotLimitsConfig = field(
        default_factory=ScenarioSnapshotLimitsConfig
    )


@dataclass(frozen=True)
class DbtConfig:
    """dbt interop configuration."""

    project_dir: str | None = None
    profiles_dir: str | None = None
    target: str | None = None
    target_path: str | None = None


@dataclass(frozen=True)
class ProjectConfig:
    """Shared project configuration loaded from sqlbuild_project.toml."""

    name: str
    adapter: str
    default_target: str | None = None
    connection: dict[str, object] = field(default_factory=dict)
    settings: SettingsConfig = field(default_factory=SettingsConfig)
    defaults: DefaultsConfig = field(default_factory=DefaultsConfig)
    path_defaults: dict[str, dict[str, object]] = field(default_factory=dict)
    vars: dict[str, str] = field(default_factory=dict)
    targets: dict[str, TargetConfig] = field(default_factory=dict)
    janitor: JanitorConfig = field(default_factory=JanitorConfig)
    snapshots: SnapshotsConfig = field(default_factory=SnapshotsConfig)
    scenario: ScenarioConfig = field(default_factory=ScenarioConfig)
    dbt: DbtConfig = field(default_factory=DbtConfig)


@dataclass(frozen=True)
class LocalConfig:
    """Local developer overrides from sqlbuild_local.toml."""

    target: str | None = None
    adapter: str | None = None
    connection: dict[str, object] = field(default_factory=dict)
    targets: dict[str, LocalTargetConfig] = field(default_factory=dict)
    settings: SettingsConfig = field(default_factory=SettingsConfig)
    setting_overrides: frozenset[str] = field(default_factory=frozenset)
    vars: dict[str, str] = field(default_factory=dict)
    scenario: ScenarioConfig = field(default_factory=ScenarioConfig)


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
                project_limits.max_rows_per_relation,
                local_limits.max_rows_per_relation,
            ),
            max_total_rows=_resolve_optional_int_override(
                project_limits.max_total_rows,
                local_limits.max_total_rows,
            ),
            max_bytes_per_relation=_resolve_optional_int_override(
                project_limits.max_bytes_per_relation,
                local_limits.max_bytes_per_relation,
            ),
            max_total_bytes=_resolve_optional_int_override(
                project_limits.max_total_bytes,
                local_limits.max_total_bytes,
            ),
        ),
    )


def _resolve_optional_int_override(
    project_value: int | None, local_value: int | None
) -> int | None:
    return local_value if local_value is not None else project_value


def scenario_local_type_overrides_for_dialect(
    *, scenario_config: ScenarioConfig, sqlglot_dialect: str | None
) -> dict[str, str]:
    """Return global and dialect-specific scenario local type override rules."""

    overrides: dict[str, str] = dict(scenario_config.local_type_overrides.get("*", {}))
    if sqlglot_dialect is not None:
        overrides.update(scenario_config.local_type_overrides.get(sqlglot_dialect, {}))
    return overrides
