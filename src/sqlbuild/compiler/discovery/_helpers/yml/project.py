"""Project config loading helpers."""

from __future__ import annotations

import tomllib
from dataclasses import fields
from datetime import date, datetime
from pathlib import Path
from typing import cast

import yaml
from yaml import YAMLError

from sqlbuild.compiler.discovery.constants import (
    CONFIG_CONCURRENCY_KEY,
    DBT_DEFER_CLONE_CONFIG_KEY,
    DBT_LEGACY_REUSE_FROM_CONFIG_KEY,
    DBT_MACRO_PATH_PREFIX,
    DBT_REPLAY_ON_CHANGE_CONFIG_KEY,
    LEGACY_CONFIG_CONCURRENCY_KEY,
    LEGACY_LOCAL_CONFIG_FILENAME,
    LEGACY_PROJECT_CONFIG_FILENAME,
    LOCAL_CONFIG_FILENAME,
    MODELS_DIRECTORY_NAME,
    PARENT_DIRECTORY_PATH_PART,
    PROJECT_CONFIG_FILENAME,
    TOML_FILE_SUFFIX,
)
from sqlbuild.compiler.discovery.exceptions import ProjectConfigError
from sqlbuild.compiler.planner.types import ContractPolicy
from sqlbuild.spec.contracts.models import (
    ClonePolicy,
    DbtConfig,
    DbtProductionRefConfig,
    DefaultsConfig,
    JanitorConfig,
    LocalClonePolicy,
    LocalConfig,
    LocalDbtConfig,
    LocalStateConfig,
    LocalTargetConfig,
    ProjectConfig,
    ScenarioConfig,
    ScenarioSnapshotLimitsConfig,
    SettingsConfig,
    SnapshotsConfig,
    StateConfig,
    TargetConfig,
)

_SNAPSHOT_FULL_REFRESH_POLICIES: frozenset[str] = frozenset(
    {"allow", "deny", "require_confirmation"}
)
_SNAPSHOT_SCHEMA_CHANGE_POLICIES: frozenset[str] = frozenset(
    {"append_new_columns", "deny", "require_confirmation"}
)
_DEFAULT_CURRENT_STATE_SNAPSHOT_FULL_REFRESH: str = "deny"
_DEFAULT_HISTORICAL_SNAPSHOT_FULL_REFRESH: str = "require_confirmation"
_DEFAULT_SNAPSHOT_SCHEMA_CHANGE: str = "append_new_columns"
_DEFAULT_WILDCARD_CHECK_SNAPSHOT_SCHEMA_CHANGE: str = "require_confirmation"


def load_project_config(*, project_dir: Path) -> ProjectConfig:
    """Load project config from the given project directory."""

    file_path: Path = _resolve_project_config_path(project_dir=project_dir)
    payload: dict[str, object] = _load_config_mapping(file_path=file_path)

    name: str = _require_str(payload=payload, key="name", file_path=file_path)
    adapter: str = _require_str(payload=payload, key="adapter", file_path=file_path)
    default_target: str | None = _optional_str(payload=payload, key="default_target")
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
    targets: dict[str, TargetConfig] = _load_targets(
        payload=payload.get("targets"),
        file_path=file_path,
    )
    janitor: JanitorConfig = _load_janitor(payload=payload.get("janitor"), file_path=file_path)
    snapshots: SnapshotsConfig = _load_snapshots(
        payload=payload.get("snapshots"), file_path=file_path
    )
    scenario: ScenarioConfig = _load_scenario(payload=payload.get("scenario"), file_path=file_path)
    dbt: DbtConfig = _load_dbt(payload=payload.get("dbt"), file_path=file_path)
    if janitor.enabled and janitor.delete_tracked_only and not settings.query_change_tracking:
        raise ProjectConfigError(
            f"{file_path} janitor.delete_tracked_only requires "
            "settings.query_change_tracking to be true"
        )

    return ProjectConfig(
        name=name,
        adapter=adapter,
        default_target=default_target,
        connection=connection,
        settings=settings,
        defaults=defaults,
        path_defaults=path_defaults,
        vars=vars_map,
        targets=targets,
        janitor=janitor,
        snapshots=snapshots,
        scenario=scenario,
        dbt=dbt,
    )


def load_local_config(*, project_dir: Path) -> LocalConfig:
    """Load local config if present."""

    file_path: Path = _resolve_local_config_path(project_dir=project_dir)
    if not file_path.exists():
        return LocalConfig()

    payload: dict[str, object] = _load_config_mapping(file_path=file_path)
    target: str | None = _optional_str(payload=payload, key="target")
    adapter: str | None = _optional_str(payload=payload, key="adapter")
    connection: dict[str, object] = _optional_mapping(payload=payload, key="connection")
    targets: dict[str, LocalTargetConfig] = _load_local_targets(
        payload=payload.get("targets"),
        file_path=file_path,
    )
    local_settings_result: tuple[SettingsConfig, frozenset[str]] = _load_local_settings(
        payload=payload.get("settings"), file_path=file_path
    )
    settings: SettingsConfig = local_settings_result[0]
    setting_overrides: frozenset[str] = local_settings_result[1]
    vars_map: dict[str, str] = _load_string_mapping(
        payload=payload.get("vars"), file_path=file_path
    )
    dbt: LocalDbtConfig = _load_local_dbt(payload=payload.get("dbt"), file_path=file_path)
    scenario: ScenarioConfig = _load_scenario(payload=payload.get("scenario"), file_path=file_path)
    return LocalConfig(
        target=target,
        adapter=adapter,
        connection=connection,
        targets=targets,
        settings=settings,
        setting_overrides=setting_overrides,
        vars=vars_map,
        dbt=dbt,
        scenario=scenario,
    )


def _resolve_project_config_path(*, project_dir: Path) -> Path:
    toml_path: Path = project_dir / PROJECT_CONFIG_FILENAME
    if toml_path.exists():
        return toml_path
    legacy_path: Path = project_dir / LEGACY_PROJECT_CONFIG_FILENAME
    if legacy_path.exists():
        raise ProjectConfigError(
            f"{legacy_path} is no longer supported. Rename it to {PROJECT_CONFIG_FILENAME} "
            "and convert the contents to TOML."
        )
    return toml_path


def _resolve_local_config_path(*, project_dir: Path) -> Path:
    toml_path: Path = project_dir / LOCAL_CONFIG_FILENAME
    if toml_path.exists():
        return toml_path
    yaml_path: Path = project_dir / LEGACY_LOCAL_CONFIG_FILENAME
    if yaml_path.exists():
        raise ProjectConfigError(
            f"{yaml_path} is no longer supported. Rename it to {LOCAL_CONFIG_FILENAME} "
            "and convert the contents to TOML."
        )
    return toml_path


def _load_config_mapping(*, file_path: Path) -> dict[str, object]:
    if file_path.suffix == TOML_FILE_SUFFIX:
        return _load_toml_mapping(file_path=file_path)
    return _load_yaml_mapping(file_path=file_path)


def _load_toml_mapping(*, file_path: Path) -> dict[str, object]:
    if not file_path.exists():
        raise ProjectConfigError(
            f"Project config not found: {file_path}. Run sqb from a sqlbuild project "
            "directory or pass --project-dir."
        )
    try:
        with file_path.open("rb") as config_file:
            payload: object = tomllib.load(config_file)
    except tomllib.TOMLDecodeError as error:
        raise ProjectConfigError(f"{file_path} contains invalid TOML: {error}") from error
    if not isinstance(payload, dict):
        raise ProjectConfigError(f"{file_path} must contain a top-level mapping")
    return cast(dict[str, object], payload)


def _load_yaml_mapping(*, file_path: Path) -> dict[str, object]:
    if not file_path.exists():
        raise ProjectConfigError(
            f"Project config not found: {file_path}. Run sqb from a sqlbuild project "
            "directory or pass --project-dir."
        )
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
    canonical_setting_names: frozenset[str] = frozenset(
        field.name for field in fields(SettingsConfig)
    )
    _validate_allowed_keys(
        mapping=mapping,
        allowed_keys=canonical_setting_names | {LEGACY_CONFIG_CONCURRENCY_KEY},
        label="settings",
        file_path=file_path,
    )
    if CONFIG_CONCURRENCY_KEY in mapping and LEGACY_CONFIG_CONCURRENCY_KEY in mapping:
        raise ProjectConfigError(
            "settings cannot define both 'concurrency' and legacy 'max_concurrency'"
        )
    sql_analysis: bool = _optional_bool(mapping=mapping, key="sql_analysis", default=True)
    query_change_tracking: bool = _optional_bool(
        mapping=mapping,
        key="query_change_tracking",
        default=True,
    )
    sql_validation: bool = _optional_bool(mapping=mapping, key="sql_validation", default=True)
    auto_load_sources: bool = _optional_bool(mapping=mapping, key="auto_load_sources", default=True)
    virtual_environments: bool = _optional_bool(
        mapping=mapping,
        key="virtual_environments",
        default=False,
    )
    changes_only: bool = _optional_bool(mapping=mapping, key="changes_only", default=False)
    concurrency_key: str = (
        LEGACY_CONFIG_CONCURRENCY_KEY
        if LEGACY_CONFIG_CONCURRENCY_KEY in mapping
        else CONFIG_CONCURRENCY_KEY
    )
    concurrency: int = _optional_int(mapping=mapping, key=concurrency_key, default=1)
    table_promotion_mode: str | None = _optional_str(payload=mapping, key="table_promotion_mode")
    default_audit_severity: str | None = _optional_str(
        payload=mapping, key="default_audit_severity"
    )
    default_audit_run_scope: str | None = _optional_str(
        payload=mapping, key="default_audit_run_scope"
    )
    return SettingsConfig(
        sql_analysis=sql_analysis,
        query_change_tracking=query_change_tracking,
        sql_validation=sql_validation,
        concurrency=concurrency,
        auto_load_sources=auto_load_sources,
        changes_only=changes_only,
        virtual_environments=virtual_environments,
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
    normalized_overrides: set[str] = set()
    key: str
    for key in mapping:
        if key == LEGACY_CONFIG_CONCURRENCY_KEY:
            normalized_overrides.add(CONFIG_CONCURRENCY_KEY)
        elif key in setting_names:
            normalized_overrides.add(key)
    return (
        _load_settings(payload=payload, file_path=file_path),
        frozenset(normalized_overrides),
    )


def _validate_allowed_keys(
    *,
    mapping: dict[str, object],
    allowed_keys: frozenset[str],
    label: str,
    file_path: Path,
) -> None:
    unknown_keys: tuple[str, ...] = tuple(sorted(key for key in mapping if key not in allowed_keys))
    if not unknown_keys:
        return
    allowed: str = ", ".join(sorted(allowed_keys))
    unknown: str = ", ".join(unknown_keys)
    raise ProjectConfigError(
        f"{file_path} {label} contains unknown key(s): {unknown}. Allowed keys: {allowed}"
    )


def _normalize_path_default_key(*, path_key: str, file_path: Path) -> str:
    normalized_key: str = path_key.strip()
    if not normalized_key:
        raise ProjectConfigError(f"{file_path} path_defaults contains an empty path key")
    if normalized_key.startswith("/"):
        raise ProjectConfigError(
            f"{file_path} path_defaults['{path_key}'] is invalid. Use model-relative paths "
            "without a leading slash, for example 'staging' or 'staging/nested'."
        )
    if normalized_key.endswith("/"):
        raise ProjectConfigError(
            f"{file_path} path_defaults['{path_key}'] is invalid. Remove the trailing slash and "
            "use a model-relative path such as 'staging' or 'staging/nested'."
        )
    path_parts: list[str] = normalized_key.split("/")
    if any(not part for part in path_parts):
        raise ProjectConfigError(
            f"{file_path} path_defaults['{path_key}'] is invalid. Path defaults cannot contain "
            "empty path segments."
        )
    if path_parts[0] == MODELS_DIRECTORY_NAME:
        raise ProjectConfigError(
            f"{file_path} path_defaults['{path_key}'] uses redundant 'models/' prefix. "
            "Use a model-relative path such as 'staging' or 'staging/nested'."
        )
    return "/".join(path_parts)


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
    row_diff_tolerances: dict[str, object] = _optional_mapping(
        payload=mapping,
        key="row_diff_tolerances",
    )
    return DefaultsConfig(
        materialized=_optional_str(payload=mapping, key="materialized"),
        database=_optional_str(payload=mapping, key="database"),
        schema=_optional_str(payload=mapping, key="schema"),
        contract=_optional_contract_policy(mapping=mapping, key="contract"),
        incremental_strategy=_optional_str(payload=mapping, key="incremental_strategy"),
        incremental_mode=_optional_str(payload=mapping, key="incremental_mode"),
        append_cursor_inclusive=_optional_templated_bool(
            mapping=mapping,
            key="append_cursor_inclusive",
        ),
        cursor_start=_optional_cursor_start(mapping=mapping, key="cursor_start"),
        lookback=_optional_str(payload=mapping, key="lookback"),
        batch_size=_optional_scalar_batch_size(mapping=mapping, key="batch_size"),
        replay_on_change=_optional_str(payload=mapping, key="replay_on_change"),
        run_despite_unchanged=_optional_str(payload=mapping, key="run_despite_unchanged"),
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
        normalized_path_key: str = _normalize_path_default_key(
            path_key=path_key, file_path=file_path
        )
        if normalized_path_key in path_defaults:
            raise ProjectConfigError(
                f"{file_path} path_defaults defines both '{path_key}' and another key that "
                f"normalize to '{normalized_path_key}'. Use only the canonical model-relative "
                "form without a leading 'models/' prefix."
            )
        path_defaults[normalized_path_key] = path_dict
    return path_defaults


def _load_targets(*, payload: object, file_path: Path) -> dict[str, TargetConfig]:
    mapping: dict[str, object] = _coerce_mapping(
        payload=payload, label="targets", file_path=file_path
    )
    targets: dict[str, TargetConfig] = {}
    target_name: str
    target_payload: object
    for target_name, target_payload in mapping.items():
        target_mapping: dict[str, object] = _coerce_mapping(
            payload=target_payload,
            label=f"targets.{target_name}",
            file_path=file_path,
        )
        clone_mapping: dict[str, object] = _coerce_mapping(
            payload=target_mapping.get("clone"),
            label=f"targets.{target_name}.clone",
            file_path=file_path,
        )
        state_mapping: dict[str, object] = _coerce_mapping(
            payload=target_mapping.get("state"),
            label=f"targets.{target_name}.state",
            file_path=file_path,
        )
        targets[target_name] = TargetConfig(
            connection=_optional_mapping(payload=target_mapping, key="connection"),
            vars=_load_string_mapping(payload=target_mapping.get("vars"), file_path=file_path),
            database=_optional_str(payload=target_mapping, key="database"),
            schema=_optional_str(payload=target_mapping, key="schema"),
            loader_schema=_optional_str(payload=target_mapping, key="loader_schema"),
            defer_sources_to=_optional_str(payload=target_mapping, key="defer_sources_to"),
            defer_clone_from=_optional_str(payload=target_mapping, key="defer_clone_from"),
            changes_only=_optional_nullable_bool(mapping=target_mapping, key="changes_only"),
            clone=ClonePolicy(
                allow_as_clone_origin=_optional_bool(
                    mapping=clone_mapping,
                    key="allow_as_clone_origin",
                    default=False,
                ),
                allow_as_clone_destination=_optional_bool(
                    mapping=clone_mapping,
                    key="allow_as_clone_destination",
                    default=False,
                ),
            ),
            state=StateConfig(
                backend=_optional_str(payload=state_mapping, key="backend"),
                schema=_optional_str(payload=state_mapping, key="schema"),
                connection=_optional_mapping(payload=state_mapping, key="connection"),
                allow_reset=_optional_bool(
                    mapping=state_mapping,
                    key="allow_reset",
                    default=False,
                ),
                unsuffixed_virtual_env=_optional_str(
                    payload=state_mapping,
                    key="unsuffixed_virtual_env",
                ),
            ),
        )
    return targets


def _load_local_targets(*, payload: object, file_path: Path) -> dict[str, LocalTargetConfig]:
    mapping: dict[str, object] = _coerce_mapping(
        payload=payload, label="targets", file_path=file_path
    )
    targets: dict[str, LocalTargetConfig] = {}
    target_name: str
    target_payload: object
    for target_name, target_payload in mapping.items():
        target_mapping: dict[str, object] = _coerce_mapping(
            payload=target_payload,
            label=f"targets.{target_name}",
            file_path=file_path,
        )
        clone_mapping: dict[str, object] = _coerce_mapping(
            payload=target_mapping.get("clone"),
            label=f"targets.{target_name}.clone",
            file_path=file_path,
        )
        state_mapping: dict[str, object] = _coerce_mapping(
            payload=target_mapping.get("state"),
            label=f"targets.{target_name}.state",
            file_path=file_path,
        )
        targets[target_name] = LocalTargetConfig(
            connection=_optional_mapping(payload=target_mapping, key="connection"),
            vars=_load_string_mapping(payload=target_mapping.get("vars"), file_path=file_path),
            database=_optional_str(payload=target_mapping, key="database"),
            schema=_optional_str(payload=target_mapping, key="schema"),
            loader_schema=_optional_str(payload=target_mapping, key="loader_schema"),
            defer_sources_to=_optional_str(payload=target_mapping, key="defer_sources_to"),
            defer_clone_from=_optional_str(payload=target_mapping, key="defer_clone_from"),
            changes_only=_optional_nullable_bool(mapping=target_mapping, key="changes_only"),
            clone=LocalClonePolicy(
                allow_as_clone_origin=_optional_nullable_bool(
                    mapping=clone_mapping,
                    key="allow_as_clone_origin",
                ),
                allow_as_clone_destination=_optional_nullable_bool(
                    mapping=clone_mapping,
                    key="allow_as_clone_destination",
                ),
            ),
            state=LocalStateConfig(
                backend=_optional_str(payload=state_mapping, key="backend"),
                schema=_optional_str(payload=state_mapping, key="schema"),
                connection=_optional_mapping(payload=state_mapping, key="connection"),
                allow_reset=_optional_nullable_bool(
                    mapping=state_mapping,
                    key="allow_reset",
                ),
                unsuffixed_virtual_env=_optional_str(
                    payload=state_mapping,
                    key="unsuffixed_virtual_env",
                ),
            ),
        )
    return targets


def _load_janitor(*, payload: object, file_path: Path) -> JanitorConfig:
    mapping: dict[str, object] = _coerce_mapping(
        payload=payload, label="janitor", file_path=file_path
    )
    enabled: bool = _optional_bool(mapping=mapping, key="enabled", default=False)
    retention_days: int = _optional_int(mapping=mapping, key="retention_days", default=30)
    max_checkpoints: int = _optional_int(mapping=mapping, key="max_checkpoints", default=20)
    direct_state_history_versions: int = _optional_int(
        mapping=mapping,
        key="direct_state_history_versions",
        default=20,
    )
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
    if max_checkpoints < 1:
        raise ProjectConfigError(f"{file_path} janitor.max_checkpoints must be >= 1")
    if direct_state_history_versions < 0:
        raise ProjectConfigError(f"{file_path} janitor.direct_state_history_versions must be >= 0")
    return JanitorConfig(
        enabled=enabled,
        retention_days=retention_days,
        max_checkpoints=max_checkpoints,
        direct_state_history_versions=direct_state_history_versions,
        delete_tracked_only=delete_tracked_only,
        exclude_patterns=exclude_patterns,
    )


def _load_snapshots(*, payload: object, file_path: Path) -> SnapshotsConfig:
    mapping: dict[str, object] = _coerce_mapping(
        payload=payload, label="snapshots", file_path=file_path
    )
    _validate_allowed_keys(
        mapping=mapping,
        allowed_keys=frozenset(
            {
                "current_state_full_refresh",
                "historical_full_refresh",
                "schema_change",
                "wildcard_check_schema_change",
            }
        ),
        label="snapshots",
        file_path=file_path,
    )
    return SnapshotsConfig(
        current_state_full_refresh=_optional_full_refresh_policy(
            mapping=mapping,
            key="current_state_full_refresh",
            default=_DEFAULT_CURRENT_STATE_SNAPSHOT_FULL_REFRESH,
        ),
        historical_full_refresh=_optional_full_refresh_policy(
            mapping=mapping,
            key="historical_full_refresh",
            default=_DEFAULT_HISTORICAL_SNAPSHOT_FULL_REFRESH,
        ),
        schema_change=_optional_snapshot_schema_change_policy(
            mapping=mapping,
            key="schema_change",
            default=_DEFAULT_SNAPSHOT_SCHEMA_CHANGE,
        ),
        wildcard_check_schema_change=_optional_snapshot_schema_change_policy(
            mapping=mapping,
            key="wildcard_check_schema_change",
            default=_DEFAULT_WILDCARD_CHECK_SNAPSHOT_SCHEMA_CHANGE,
        ),
    )


def _load_scenario(*, payload: object, file_path: Path) -> ScenarioConfig:
    mapping: dict[str, object] = _coerce_mapping(
        payload=payload, label="scenario", file_path=file_path
    )
    _validate_allowed_keys(
        mapping=mapping,
        allowed_keys=frozenset({"local_type_overrides", "snapshot_limits"}),
        label="scenario",
        file_path=file_path,
    )
    overrides_payload: dict[str, object] = _coerce_mapping(
        payload=mapping.get("local_type_overrides"),
        label="scenario.local_type_overrides",
        file_path=file_path,
    )
    local_type_overrides: dict[str, dict[str, str]] = {}
    dialect: str
    rules_payload: object
    for dialect, rules_payload in overrides_payload.items():
        if not isinstance(dialect, str) or not dialect.strip():
            raise ProjectConfigError(
                f"{file_path} scenario.local_type_overrides contains an empty dialect key"
            )
        local_type_overrides[dialect.strip()] = _load_string_mapping(
            payload=rules_payload,
            file_path=file_path,
        )
    return ScenarioConfig(
        local_type_overrides=local_type_overrides,
        snapshot_limits=_load_scenario_snapshot_limits(
            payload=mapping.get("snapshot_limits"),
            file_path=file_path,
        ),
    )


def _load_dbt(*, payload: object, file_path: Path) -> DbtConfig:
    """Load optional dbt interop configuration."""

    mapping: dict[str, object] = _coerce_mapping(payload=payload, label="dbt", file_path=file_path)
    if DBT_LEGACY_REUSE_FROM_CONFIG_KEY in mapping:
        raise ProjectConfigError(
            f"{file_path} [dbt.reuse_from] was renamed to [dbt.production_ref]; "
            "rename the table and its keys accordingly"
        )
    removed_keys: tuple[str, ...] = tuple(
        key
        for key in (DBT_DEFER_CLONE_CONFIG_KEY, DBT_REPLAY_ON_CHANGE_CONFIG_KEY)
        if key in mapping
    )
    if removed_keys:
        raise ProjectConfigError(
            f"{file_path} [dbt] option(s) were removed: {', '.join(removed_keys)}; "
            "use dbt-native --state/--defer or explicit sqb dbt clone"
        )
    _validate_allowed_keys(
        mapping=mapping,
        allowed_keys=frozenset(
            {
                "project_dir",
                "profiles_dir",
                "target",
                "target_path",
                "vars",
                "production_ref",
            }
        ),
        label="dbt",
        file_path=file_path,
    )
    return DbtConfig(
        project_dir=_optional_str(payload=mapping, key="project_dir"),
        profiles_dir=_optional_str(payload=mapping, key="profiles_dir"),
        target=_optional_str(payload=mapping, key="target"),
        target_path=_optional_str(payload=mapping, key="target_path"),
        vars=_load_object_mapping(payload=mapping.get("vars"), file_path=file_path),
        production_ref=_load_dbt_production_ref(
            payload=mapping.get("production_ref"),
            file_path=file_path,
        ),
    )


def _load_local_dbt(*, payload: object, file_path: Path) -> LocalDbtConfig:
    """Load optional local dbt interop configuration."""

    mapping: dict[str, object] = _coerce_mapping(payload=payload, label="dbt", file_path=file_path)
    if DBT_DEFER_CLONE_CONFIG_KEY in mapping:
        raise ProjectConfigError(
            f"{file_path} [dbt].defer_clone_from was removed; "
            "use dbt-native --state/--defer or explicit sqb dbt clone"
        )
    _validate_allowed_keys(
        mapping=mapping,
        allowed_keys=frozenset({"target", "vars"}),
        label="dbt",
        file_path=file_path,
    )
    return LocalDbtConfig(
        target=_optional_str(payload=mapping, key="target"),
        vars=_load_object_mapping(payload=mapping.get("vars"), file_path=file_path),
    )


def _load_dbt_production_ref(*, payload: object, file_path: Path) -> DbtProductionRefConfig:
    mapping: dict[str, object] = _coerce_mapping(
        payload=payload,
        label="dbt.production_ref",
        file_path=file_path,
    )
    _validate_allowed_keys(
        mapping=mapping,
        allowed_keys=frozenset(
            {"git_ref", "generate_schema_name_override", "refresh", "git_timeout_seconds"}
        ),
        label="dbt.production_ref",
        file_path=file_path,
    )
    if not mapping:
        return DbtProductionRefConfig()

    git_ref: str = _require_str(payload=mapping, key="git_ref", file_path=file_path)
    generate_schema_name_override: str = _require_str(
        payload=mapping,
        key="generate_schema_name_override",
        file_path=file_path,
    )
    _validate_dbt_production_ref_macro_path(
        value=generate_schema_name_override,
        file_path=file_path,
    )
    git_timeout_seconds: int = _optional_int(
        mapping=mapping,
        key="git_timeout_seconds",
        default=30,
    )
    if git_timeout_seconds <= 0:
        raise ProjectConfigError(f"{file_path} dbt.production_ref.git_timeout_seconds must be > 0")
    return DbtProductionRefConfig(
        git_ref=git_ref,
        generate_schema_name_override=generate_schema_name_override,
        refresh=_optional_bool(mapping=mapping, key="refresh", default=True),
        git_timeout_seconds=git_timeout_seconds,
    )


def _validate_dbt_production_ref_macro_path(*, value: str, file_path: Path) -> None:
    macro_path: Path = Path(value)
    if macro_path.is_absolute() or PARENT_DIRECTORY_PATH_PART in macro_path.parts:
        raise ProjectConfigError(
            f"{file_path} dbt.production_ref.generate_schema_name_override must be a relative "
            "path under dbt/macros/"
        )
    dbt_macro_path_part_count: int = 3
    if (
        len(macro_path.parts) < dbt_macro_path_part_count
        or macro_path.parts[:2] != DBT_MACRO_PATH_PREFIX
    ):
        raise ProjectConfigError(
            f"{file_path} dbt.production_ref.generate_schema_name_override must be under "
            "dbt/macros/"
        )
    resolved_macro_path: Path = file_path.parent / macro_path
    if not resolved_macro_path.is_file():
        raise ProjectConfigError(
            f"{file_path} dbt.production_ref.generate_schema_name_override file not found: "
            f"{resolved_macro_path}"
        )


def _load_scenario_snapshot_limits(
    *, payload: object, file_path: Path
) -> ScenarioSnapshotLimitsConfig:
    mapping: dict[str, object] = _coerce_mapping(
        payload=payload,
        label="scenario.snapshot_limits",
        file_path=file_path,
    )
    _validate_allowed_keys(
        mapping=mapping,
        allowed_keys=frozenset(
            {
                "max_rows_per_relation",
                "max_total_rows",
                "max_bytes_per_relation",
                "max_total_bytes",
            }
        ),
        label="scenario.snapshot_limits",
        file_path=file_path,
    )
    limits: ScenarioSnapshotLimitsConfig = ScenarioSnapshotLimitsConfig(
        max_rows_per_relation=_optional_nullable_int(
            mapping=mapping,
            key="max_rows_per_relation",
        ),
        max_total_rows=_optional_nullable_int(mapping=mapping, key="max_total_rows"),
        max_bytes_per_relation=_optional_nullable_int(
            mapping=mapping,
            key="max_bytes_per_relation",
        ),
        max_total_bytes=_optional_nullable_int(mapping=mapping, key="max_total_bytes"),
    )
    value: int | None
    for value in (
        limits.max_rows_per_relation,
        limits.max_total_rows,
        limits.max_bytes_per_relation,
        limits.max_total_bytes,
    ):
        if value is not None and value < 0:
            raise ProjectConfigError(f"{file_path} scenario.snapshot_limits values must be >= 0")
    return limits


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


def _load_object_mapping(*, payload: object, file_path: Path) -> dict[str, object]:
    mapping: dict[str, object] = _coerce_mapping(
        payload=payload, label="mapping", file_path=file_path
    )
    return dict(mapping)


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


def _optional_nullable_bool(*, mapping: dict[str, object], key: str) -> bool | None:
    value: object | None = mapping.get(key)
    if value is None:
        return None
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


def _optional_nullable_int(*, mapping: dict[str, object], key: str) -> int | None:
    value: object | None = mapping.get(key)
    if value is None:
        return None
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


def _optional_full_refresh_policy(*, mapping: dict[str, object], key: str, default: str) -> str:
    value: object | None = mapping.get(key)
    if value is None:
        return default
    if not isinstance(value, str):
        raise ProjectConfigError(f"Expected '{key}' to be a string when provided")
    if value not in _SNAPSHOT_FULL_REFRESH_POLICIES:
        valid_values: str = ", ".join(sorted(_SNAPSHOT_FULL_REFRESH_POLICIES))
        raise ProjectConfigError(f"Expected '{key}' to be one of: {valid_values}")
    return value


def _optional_snapshot_schema_change_policy(
    *, mapping: dict[str, object], key: str, default: str
) -> str:
    value: object | None = mapping.get(key)
    if value is None:
        return default
    if not isinstance(value, str):
        raise ProjectConfigError(f"Expected '{key}' to be a string when provided")
    if value not in _SNAPSHOT_SCHEMA_CHANGE_POLICIES:
        valid_values: str = ", ".join(sorted(_SNAPSHOT_SCHEMA_CHANGE_POLICIES))
        raise ProjectConfigError(f"Expected '{key}' to be one of: {valid_values}")
    return value


def _optional_contract_policy(*, mapping: dict[str, object], key: str) -> str | None:
    value: object | None = mapping.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ProjectConfigError(f"Expected '{key}' to be a string when provided")
    if value not in ContractPolicy:
        raise ProjectConfigError("Expected 'contract' to be one of: enforced, none")
    return value


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
