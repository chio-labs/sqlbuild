"""Project config loading helpers."""

from __future__ import annotations

from dataclasses import fields
from datetime import date, datetime
from pathlib import Path
from typing import cast

import yaml
from yaml import YAMLError

from sqlbuild.compiler.discovery.exceptions import ProjectConfigError
from sqlbuild.spec.models.project import (
    ClonePolicy,
    DefaultsConfig,
    EnvironmentConfig,
    JanitorConfig,
    LocalConfig,
    ProjectConfig,
    SettingsConfig,
)


def load_project_config(*, project_dir: Path) -> ProjectConfig:
    """Load `sqlbuild_project.yml` from the given project directory."""

    file_path: Path = project_dir / "sqlbuild_project.yml"
    payload: dict[str, object] = _load_yaml_mapping(file_path=file_path)

    name: str = _require_str(payload=payload, key="name", file_path=file_path)
    adapter: str = _require_str(payload=payload, key="adapter", file_path=file_path)
    default_environment: str | None = _optional_str(payload=payload, key="default_environment")
    connection: dict[str, object] = _optional_mapping(payload=payload, key="connection")
    settings: SettingsConfig = _load_settings(payload=payload.get("settings"), file_path=file_path)
    defaults: DefaultsConfig = _load_defaults(payload=payload.get("defaults"), file_path=file_path)
    path_defaults: dict[str, dict[str, object]] = _load_path_defaults(
        payload=payload.get("path_defaults"),
        file_path=file_path,
    )
    vars_map: dict[str, str] = _load_string_mapping(
        payload=payload.get("vars"), file_path=file_path
    )
    environments: dict[str, EnvironmentConfig] = _load_environments(
        payload=payload.get("environments"),
        file_path=file_path,
    )
    janitor: JanitorConfig = _load_janitor(payload=payload.get("janitor"), file_path=file_path)
    if janitor.enabled and janitor.delete_tracked_only and not settings.query_change_tracking:
        raise ProjectConfigError(
            f"{file_path} janitor.delete_tracked_only requires "
            "settings.query_change_tracking to be true"
        )

    return ProjectConfig(
        name=name,
        adapter=adapter,
        default_environment=default_environment,
        connection=connection,
        settings=settings,
        defaults=defaults,
        path_defaults=path_defaults,
        vars=vars_map,
        environments=environments,
        janitor=janitor,
    )


def load_local_config(*, project_dir: Path) -> LocalConfig:
    """Load `sqlbuild_local.yml` if present."""

    file_path: Path = project_dir / "sqlbuild_local.yml"
    if not file_path.exists():
        return LocalConfig()

    payload: dict[str, object] = _load_yaml_mapping(file_path=file_path)
    environment: str | None = _optional_str(payload=payload, key="environment")
    connection: dict[str, object] = _optional_mapping(payload=payload, key="connection")
    local_settings_result: tuple[SettingsConfig, frozenset[str]] = _load_local_settings(
        payload=payload.get("settings"), file_path=file_path
    )
    settings: SettingsConfig = local_settings_result[0]
    setting_overrides: frozenset[str] = local_settings_result[1]
    vars_map: dict[str, str] = _load_string_mapping(
        payload=payload.get("vars"), file_path=file_path
    )
    return LocalConfig(
        environment=environment,
        connection=connection,
        settings=settings,
        setting_overrides=setting_overrides,
        vars=vars_map,
    )


def _load_yaml_mapping(*, file_path: Path) -> dict[str, object]:
    contents: str = file_path.read_text(encoding="utf-8")
    try:
        payload: object = yaml.safe_load(contents)
    except YAMLError as error:
        raise ProjectConfigError(f"{file_path} contains invalid YAML: {error}") from error
    if payload is None:
        return {}
    if not isinstance(payload, dict):
        raise ProjectConfigError(f"{file_path} must contain a top-level mapping")
    return cast(dict[str, object], payload)


def _require_str(*, payload: dict[str, object], key: str, file_path: Path) -> str:
    value: object | None = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ProjectConfigError(f"{file_path} must define non-empty string '{key}'")
    return value.strip()


def _optional_str(*, payload: dict[str, object], key: str) -> str | None:
    value: object | None = payload.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ProjectConfigError(f"Expected '{key}' to be a non-empty string when provided")
    return value.strip()


def _optional_mapping(*, payload: dict[str, object], key: str) -> dict[str, object]:
    value: object | None = payload.get(key)
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ProjectConfigError(f"Expected '{key}' to be a mapping when provided")
    return cast(dict[str, object], value)


def _load_settings(*, payload: object, file_path: Path) -> SettingsConfig:
    mapping: dict[str, object] = _coerce_mapping(
        payload=payload, label="settings", file_path=file_path
    )
    sqlglot: bool = _optional_bool(mapping=mapping, key="sqlglot", default=True)
    query_change_tracking: bool = _optional_bool(
        mapping=mapping,
        key="query_change_tracking",
        default=True,
    )
    sql_validation: bool = _optional_bool(mapping=mapping, key="sql_validation", default=True)
    max_concurrency: int = _optional_int(mapping=mapping, key="max_concurrency", default=1)
    table_promotion_mode: str | None = _optional_str(payload=mapping, key="table_promotion_mode")
    default_audit_severity: str | None = _optional_str(
        payload=mapping, key="default_audit_severity"
    )
    default_audit_run_scope: str | None = _optional_str(
        payload=mapping, key="default_audit_run_scope"
    )
    return SettingsConfig(
        sqlglot=sqlglot,
        query_change_tracking=query_change_tracking,
        sql_validation=sql_validation,
        max_concurrency=max_concurrency,
        table_promotion_mode=table_promotion_mode,
        default_audit_severity=default_audit_severity,
        default_audit_run_scope=default_audit_run_scope,
    )


def _load_local_settings(
    *, payload: object, file_path: Path
) -> tuple[SettingsConfig, frozenset[str]]:
    mapping: dict[str, object] = _coerce_mapping(
        payload=payload, label="settings", file_path=file_path
    )
    setting_names: frozenset[str] = frozenset(field.name for field in fields(SettingsConfig))
    return (
        _load_settings(payload=payload, file_path=file_path),
        frozenset(key for key in mapping if key in setting_names),
    )


def _load_defaults(*, payload: object, file_path: Path) -> DefaultsConfig:
    mapping: dict[str, object] = _coerce_mapping(
        payload=payload, label="defaults", file_path=file_path
    )
    row_diff_exclude_columns: tuple[str, ...] = tuple(
        _load_string_sequence(
            payload=mapping.get("row_diff_exclude_columns"),
            label="defaults.row_diff_exclude_columns",
            file_path=file_path,
        )
    )
    tags: tuple[str, ...] = tuple(
        _load_string_sequence(
            payload=mapping.get("tags"),
            label="defaults.tags",
            file_path=file_path,
        )
    )
    schema_change_backfill: dict[str, str] = _load_string_mapping(
        payload=mapping.get("schema_change_backfill"),
        file_path=file_path,
    )
    row_diff_tolerances: dict[str, object] = _optional_mapping(
        payload=mapping,
        key="row_diff_tolerances",
    )
    return DefaultsConfig(
        materialized=_optional_str(payload=mapping, key="materialized"),
        database=_optional_str(payload=mapping, key="database"),
        schema=_optional_str(payload=mapping, key="schema"),
        incremental_strategy=_optional_str(payload=mapping, key="incremental_strategy"),
        incremental_mode=_optional_str(payload=mapping, key="incremental_mode"),
        append_cursor_inclusive=_optional_templated_bool(
            mapping=mapping,
            key="append_cursor_inclusive",
        ),
        cursor_start=_optional_cursor_start(mapping=mapping, key="cursor_start"),
        lookback=_optional_str(payload=mapping, key="lookback"),
        batch_size=_optional_scalar_batch_size(mapping=mapping, key="batch_size"),
        query_change_backfill=_optional_str(payload=mapping, key="query_change_backfill"),
        schema_change_backfill=schema_change_backfill,
        row_diff_exclude_columns=row_diff_exclude_columns,
        row_diff_tolerances=row_diff_tolerances,
        tags=tags,
    )


def _load_path_defaults(*, payload: object, file_path: Path) -> dict[str, dict[str, object]]:
    mapping: dict[str, object] = _coerce_mapping(
        payload=payload, label="path_defaults", file_path=file_path
    )
    path_defaults: dict[str, dict[str, object]] = {}
    path_key: str
    path_value: object
    for path_key, path_value in mapping.items():
        if not isinstance(path_value, dict):
            raise ProjectConfigError(f"{file_path} path_defaults['{path_key}'] must be a mapping")
        path_dict: dict[str, object] = cast(dict[str, object], path_value)
        _validate_path_default_tags(path_dict=path_dict, path_key=path_key, file_path=file_path)
        path_defaults[path_key] = path_dict
    return path_defaults


def _load_environments(*, payload: object, file_path: Path) -> dict[str, EnvironmentConfig]:
    mapping: dict[str, object] = _coerce_mapping(
        payload=payload, label="environments", file_path=file_path
    )
    environments: dict[str, EnvironmentConfig] = {}
    env_name: str
    env_payload: object
    for env_name, env_payload in mapping.items():
        env_mapping: dict[str, object] = _coerce_mapping(
            payload=env_payload,
            label=f"environments.{env_name}",
            file_path=file_path,
        )
        clone_mapping: dict[str, object] = _coerce_mapping(
            payload=env_mapping.get("clone"),
            label=f"environments.{env_name}.clone",
            file_path=file_path,
        )
        environments[env_name] = EnvironmentConfig(
            connection=_optional_mapping(payload=env_mapping, key="connection"),
            vars=_load_string_mapping(payload=env_mapping.get("vars"), file_path=file_path),
            database=_optional_str(payload=env_mapping, key="database"),
            schema=_optional_str(payload=env_mapping, key="schema"),
            clone=ClonePolicy(
                allow_as_source=_optional_bool(
                    mapping=clone_mapping,
                    key="allow_as_source",
                    default=False,
                ),
                allow_as_target=_optional_bool(
                    mapping=clone_mapping,
                    key="allow_as_target",
                    default=False,
                ),
            ),
        )
    return environments


def _load_janitor(*, payload: object, file_path: Path) -> JanitorConfig:
    mapping: dict[str, object] = _coerce_mapping(
        payload=payload, label="janitor", file_path=file_path
    )
    enabled: bool = _optional_bool(mapping=mapping, key="enabled", default=False)
    retention_days: int = _optional_int(mapping=mapping, key="retention_days", default=30)
    delete_tracked_only: bool = _optional_bool(
        mapping=mapping,
        key="delete_tracked_only",
        default=True,
    )
    exclude_patterns: tuple[str, ...] = tuple(
        _load_string_sequence(
            payload=mapping.get("exclude_patterns"),
            label="janitor.exclude_patterns",
            file_path=file_path,
        )
    )
    if retention_days < 0:
        raise ProjectConfigError(f"{file_path} janitor.retention_days must be >= 0")
    return JanitorConfig(
        enabled=enabled,
        retention_days=retention_days,
        delete_tracked_only=delete_tracked_only,
        exclude_patterns=exclude_patterns,
    )


def _load_string_mapping(*, payload: object, file_path: Path) -> dict[str, str]:
    mapping: dict[str, object] = _coerce_mapping(
        payload=payload, label="mapping", file_path=file_path
    )
    result: dict[str, str] = {}
    key: str
    value: object
    for key, value in mapping.items():
        if not isinstance(value, str):
            raise ProjectConfigError(f"{file_path} expected string value for '{key}'")
        result[key] = value
    return result


def _load_string_sequence(*, payload: object, label: str, file_path: Path) -> list[str]:
    if payload is None:
        return []
    if not isinstance(payload, list):
        raise ProjectConfigError(f"{file_path} {label} must be a list of strings")
    values: list[str] = []
    item: object
    for item in payload:
        if not isinstance(item, str):
            raise ProjectConfigError(f"{file_path} {label} must contain only strings")
        values.append(item)
    return values


def _coerce_mapping(*, payload: object, label: str, file_path: Path) -> dict[str, object]:
    if payload is None:
        return {}
    if not isinstance(payload, dict):
        raise ProjectConfigError(f"{file_path} {label} must be a mapping")
    return cast(dict[str, object], payload)


def _optional_bool(*, mapping: dict[str, object], key: str, default: bool) -> bool:
    value: object | None = mapping.get(key)
    if value is None:
        return default
    if not isinstance(value, bool):
        raise ProjectConfigError(f"Expected '{key}' to be a boolean when provided")
    return value


def _optional_templated_bool(*, mapping: dict[str, object], key: str) -> object | None:
    value: object | None = mapping.get(key)
    if value is None:
        return None
    if not isinstance(value, bool | str):
        raise ProjectConfigError(f"Expected '{key}' to be a boolean when provided")
    return value


def _optional_int(*, mapping: dict[str, object], key: str, default: int) -> int:
    value: object | None = mapping.get(key)
    if value is None:
        return default
    if not isinstance(value, int):
        raise ProjectConfigError(f"Expected '{key}' to be an integer when provided")
    return value


def _optional_scalar_batch_size(*, mapping: dict[str, object], key: str) -> str | int | None:
    value: object | None = mapping.get(key)
    if value is None:
        return None
    if isinstance(value, (str, int)):
        return value
    raise ProjectConfigError(f"Expected '{key}' to be a string or integer when provided")


def _optional_cursor_start(*, mapping: dict[str, object], key: str) -> object | None:
    value: object | None = mapping.get(key)
    if value is None:
        return None
    if isinstance(value, str | int | date | datetime):
        return value
    raise ProjectConfigError(
        f"Expected '{key}' to be a string, integer, or date-like value when provided"
    )


def _validate_path_default_tags(
    *,
    path_dict: dict[str, object],
    path_key: str,
    file_path: Path,
) -> None:
    """Validate that tags in a path_defaults entry is a list of strings."""

    raw_tags: object | None = path_dict.get("tags")
    if raw_tags is None:
        return
    if not isinstance(raw_tags, list):
        raise ProjectConfigError(f"{file_path} path_defaults['{path_key}'].tags must be a list")
    item: object
    for item in raw_tags:
        if not isinstance(item, str):
            raise ProjectConfigError(
                f"{file_path} path_defaults['{path_key}'].tags entries must be strings"
            )
