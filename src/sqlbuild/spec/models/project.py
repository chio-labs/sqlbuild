"""Project configuration models."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ClonePolicy:
    """Environment clone policy."""

    allow_as_source: bool = False
    allow_as_target: bool = False


@dataclass(frozen=True)
class EnvironmentConfig:
    """One named environment configuration."""

    connection: dict[str, object] = field(default_factory=dict)
    vars: dict[str, str] = field(default_factory=dict)
    database: str | None = None
    schema: str | None = None
    clone: ClonePolicy = field(default_factory=ClonePolicy)


@dataclass(frozen=True)
class SettingsConfig:
    """Global feature toggles."""

    sqlglot: bool = True
    query_change_tracking: bool = True
    sql_validation: bool = True
    max_concurrency: int = 1
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
    append_cursor_inclusive: bool | None = None
    cursor_start: object | None = None
    lookback: str | None = None
    batch_size: str | int | None = None
    query_change_backfill: str | None = None
    schema_change_backfill: dict[str, str] = field(default_factory=dict)
    row_diff_exclude_columns: tuple[str, ...] = field(default_factory=tuple)
    row_diff_tolerances: dict[str, object] = field(default_factory=dict)
    tags: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class JanitorConfig:
    """Janitor command defaults."""

    enabled: bool = False
    retention_days: int = 30
    delete_tracked_only: bool = True
    exclude_patterns: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class ProjectConfig:
    """Shared project configuration loaded from sqlbuild_project.yml."""

    name: str
    adapter: str
    default_environment: str | None = None
    connection: dict[str, object] = field(default_factory=dict)
    settings: SettingsConfig = field(default_factory=SettingsConfig)
    defaults: DefaultsConfig = field(default_factory=DefaultsConfig)
    path_defaults: dict[str, dict[str, object]] = field(default_factory=dict)
    vars: dict[str, str] = field(default_factory=dict)
    environments: dict[str, EnvironmentConfig] = field(default_factory=dict)
    janitor: JanitorConfig = field(default_factory=JanitorConfig)


@dataclass(frozen=True)
class LocalConfig:
    """Local developer overrides from sqlbuild_local.yml."""

    environment: str | None = None
    vars: dict[str, str] = field(default_factory=dict)
