"""Structured project specification models."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

from sqlbuild.cost.constants import DEFAULT_USD_PER_CREDIT
from sqlbuild.spec.contracts.types import (
    SourceFreshnessStrategy,
    SourceFreshnessValueKind,
    SourceWriteStrategy,
)


@dataclass(frozen=True)
class ClonePolicy:
    """Environment clone policy."""

    allow_as_clone_origin: bool = False
    allow_as_clone_destination: bool = False


@dataclass(frozen=True)
class LocalClonePolicy:
    """Local environment clone policy overrides."""

    allow_as_clone_origin: bool | None = None
    allow_as_clone_destination: bool | None = None


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
    loader_schema: str | None = None
    defer_sources_to: str | None = None
    defer_clone_from: str | None = None
    changes_only: bool | None = None
    clone: ClonePolicy = field(default_factory=ClonePolicy)
    state: StateConfig = field(default_factory=StateConfig)


@dataclass(frozen=True)
class LocalTargetConfig:
    """Local developer overrides for one named target."""

    connection: dict[str, object] = field(default_factory=dict)
    vars: dict[str, str] = field(default_factory=dict)
    database: str | None = None
    schema: str | None = None
    loader_schema: str | None = None
    defer_sources_to: str | None = None
    defer_clone_from: str | None = None
    changes_only: bool | None = None
    clone: LocalClonePolicy = field(default_factory=LocalClonePolicy)
    state: LocalStateConfig = field(default_factory=LocalStateConfig)


@dataclass(frozen=True)
class SettingsConfig:
    """Global feature toggles."""

    sql_analysis: bool = True
    query_change_tracking: bool = True
    sql_validation: bool = True
    concurrency: int = 1
    auto_load_sources: bool = True
    changes_only: bool = False
    virtual_environments: bool = False
    table_promotion_mode: str | None = None
    default_audit_severity: str | None = None
    default_audit_run_scope: str | None = None


@dataclass(frozen=True)
class CostConfig:
    """Snowflake compute estimate configuration."""

    usd_per_credit: Decimal = DEFAULT_USD_PER_CREDIT
    usd_per_credit_is_default: bool = True


@dataclass(frozen=True)
class DefaultsConfig:
    """Project-wide model defaults."""

    materialized: str | None = None
    database: str | None = None
    schema: str | None = None
    incremental_strategy: str | None = None
    incremental_mode: str | None = None
    merge_exclude_columns: tuple[str, ...] = field(default_factory=tuple)
    allow_full_refresh: bool | None = None
    append_cursor_inclusive: object | None = None
    cursor_start: object | None = None
    lookback: str | None = None
    batch_size: str | int | None = None
    replay_on_change: str | None = None
    run_despite_unchanged: str | None = None
    row_diff_exclude_columns: tuple[str, ...] = field(default_factory=tuple)
    row_diff_tolerances: dict[str, object] = field(default_factory=dict)
    tags: tuple[str, ...] = field(default_factory=tuple)
    contract: str | None = None
    pre_hooks: object | None = None
    post_hooks: object | None = None


@dataclass(frozen=True)
class JanitorConfig:
    """Janitor command defaults."""

    enabled: bool = False
    retention_days: int = 30
    max_checkpoints: int = 20
    direct_state_history_versions: int = 20
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
    vars: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class LocalDbtConfig:
    """Local dbt interop configuration overrides."""

    target: str | None = None
    vars: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class ProjectConfig:
    """Shared project configuration loaded from sqlbuild_project.toml."""

    name: str
    adapter: str
    default_target: str | None = None
    connection: dict[str, object] = field(default_factory=dict)
    settings: SettingsConfig = field(default_factory=SettingsConfig)
    cost: CostConfig = field(default_factory=CostConfig)
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
    dbt: LocalDbtConfig = field(default_factory=LocalDbtConfig)
    scenario: ScenarioConfig = field(default_factory=ScenarioConfig)


@dataclass(frozen=True)
class SourceLocation:
    """An authored source location for compiler diagnostics."""

    path: Path
    line: int
    column: int
    end_line: int | None = None
    end_column: int | None = None


@dataclass(frozen=True)
class SeedCsvSettings:
    """CSV reader settings for a seed file."""

    delimiter: str | None = None
    quotechar: str | None = None
    doublequote: bool | None = None
    escapechar: str | None = None
    skipinitialspace: bool | None = None
    lineterminator: str | None = None
    encoding: str | None = None
    na_values: tuple[object, ...] | dict[str, tuple[object, ...]] | None = None
    keep_default_na: bool | None = None


@dataclass(frozen=True)
class SchemaAuditInstance:
    """One audit instance attached to model, column, or seed metadata."""

    definition_name: str
    arguments: dict[str, object] = field(default_factory=dict)
    name: str | None = None
    description: str | None = None
    severity: str | None = None
    run_scope: str | None = None
    always_run: bool = False
    location: SourceLocation | None = field(default=None, compare=False, repr=False)


@dataclass(frozen=True)
class SchemaColumn:
    """One declared model, seed, or source column entry."""

    name: str
    type: str | None = None
    nullable: bool | None = None
    description: str | None = None
    meta: dict[str, object] = field(default_factory=dict)
    audits: tuple[SchemaAuditInstance, ...] = field(default_factory=tuple)
    location: SourceLocation | None = None


@dataclass(frozen=True)
class SchemaModelEntry:
    """One model metadata entry normalized from MODEL(...)."""

    name: str
    model_schema: str | None = None
    description: str | None = None
    type_enforcement: bool | None = None
    meta: dict[str, object] = field(default_factory=dict)
    columns: tuple[SchemaColumn, ...] = field(default_factory=tuple)
    audits: tuple[SchemaAuditInstance, ...] = field(default_factory=tuple)
    tags: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class SchemaSeedEntry:
    """One seed metadata entry from seed YAML."""

    name: str
    description: str | None = None
    database: str | None = None
    schema: str | None = None
    meta: dict[str, object] = field(default_factory=dict)
    csv_settings: SeedCsvSettings = field(default_factory=SeedCsvSettings)
    columns: tuple[SchemaColumn, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class IntegrationLoaderConfig:
    """Typed configuration for one declarative integration loader."""

    kind: str
    config: object


@dataclass(frozen=True)
class SourceFreshnessAgePolicy:
    """Age-based source freshness warning/error thresholds."""

    warn_after: str | None = None
    error_after: str | None = None


@dataclass(frozen=True)
class SourceFreshnessConfig:
    """Configured source freshness observation for virtual planning."""

    strategy: SourceFreshnessStrategy
    value_kind: SourceFreshnessValueKind | None = None
    column: str | None = None
    query: str | None = None
    filter: str | None = None
    lag_tolerance: str | None = None
    age_policy: SourceFreshnessAgePolicy | None = None


@dataclass(frozen=True)
class SourceColumnEntry:
    """One source column entry from sources/*.yml."""

    name: str
    type: str | None = None
    nullable: bool | None = None
    description: str | None = None
    meta: dict[str, object] = field(default_factory=dict)
    audits: tuple[SchemaAuditInstance, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class SourceEntry:
    """One source declaration from sources/*.yml."""

    name: str
    database: str | None = None
    schema: str | None = None
    table: str | None = None
    loader: str | None = None
    managed: bool = False
    integration_loader: IntegrationLoaderConfig | None = None
    freshness: SourceFreshnessConfig | None = None
    write_strategy: SourceWriteStrategy | None = None
    load_batch_size: int | None = None
    cursor_column: str | None = None
    unique_key: tuple[str, ...] = field(default_factory=tuple)
    expression: str | None = None
    description: str | None = None
    type_enforcement: bool | None = None
    contract: str | None = None
    meta: dict[str, object] = field(default_factory=dict)
    columns: tuple[SourceColumnEntry, ...] = field(default_factory=tuple)
    audits: tuple[SchemaAuditInstance, ...] = field(default_factory=tuple)
