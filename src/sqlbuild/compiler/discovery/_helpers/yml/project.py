"""Project config loading helpers."""

from __future__ import annotations

import tomllib
from dataclasses import fields
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import cast

import yaml
from yaml import YAMLError

from sqlbuild.compiler.auditing.types import AuditSeverity
from sqlbuild.compiler.compile.constants import MAX_MICROBATCHES_CONFIG_KEY
from sqlbuild.compiler.discovery.constants import (
    CONFIG_CONCURRENCY_KEY,
    DBT_DEFER_CLONE_CONFIG_KEY,
    DBT_LEGACY_REUSE_FROM_CONFIG_KEY,
    DBT_PRODUCTION_REF_CONFIG_KEY,
    DBT_REPLAY_ON_CHANGE_CONFIG_KEY,
    LEGACY_CONFIG_CONCURRENCY_KEY,
    LEGACY_LOCAL_CONFIG_FILENAME,
    LEGACY_PROJECT_CONFIG_FILENAME,
    LOCAL_CONFIG_FILENAME,
    MODELS_DIRECTORY_NAME,
    PROJECT_CONFIG_FILENAME,
    TOML_FILE_SUFFIX,
)
from sqlbuild.compiler.discovery.exceptions import ProjectConfigError
from sqlbuild.compiler.path_defaults.constants import GLOB_SEGMENTS, UNSUPPORTED_GLOB_MARKERS
from sqlbuild.compiler.planner.types import ContractPolicy
from sqlbuild.cost.constants import USD_PER_CREDIT_CONFIG_KEY
from sqlbuild.cursor_algebra.constants import DURATION_DAY_UNIT
from sqlbuild.cursor_algebra.models import Duration
from sqlbuild.spec.contracts.constants import (
    TIME_TRAVEL_RETENTION_MATERIALIZATIONS,
    ZERO_DAY_CURSOR_DURATION,
)
from sqlbuild.spec.contracts.models import (
    AuthoredTimeTravelRetention,
    ClonePolicy,
    ConstantsConfig,
    CostConfig,
    CursorsConfig,
    DbtConfig,
    DefaultsConfig,
    FutureCursorsConfig,
    JanitorConfig,
    LifecycleEventSinkFilterConfig,
    LifecycleEventSinksConfig,
    LocalClonePolicy,
    LocalConfig,
    LocalDbtConfig,
    LocalStateConfig,
    LocalTargetConfig,
    MaterializationDefaultsConfig,
    MaterializationRetentionDefaults,
    MicrobatchesConfig,
    MicrobatchLimitsConfig,
    ProjectConfig,
    ScenarioConfig,
    ScenarioSnapshotLimitsConfig,
    ScopesConfig,
    SettingsConfig,
    SinksConfig,
    SnapshotsConfig,
    StartCursorsConfig,
    StateConfig,
    TargetConfig,
)
from sqlbuild.spec.contracts.types import (
    ColumnContractMode,
    EventExportSeverity,
    FutureCursorAction,
    MicrobatchLimitAction,
    TableType,
    TableTypeDowngradePolicy,
    TableTypeValue,
    TimeTravelRetentionValue,
)
from sqlbuild.sql_values.types import CollectionRendering

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
_BATCH_CONCURRENCY_CONFIG_KEY: str = "batch_concurrency"
_MAX_BATCHES_CONFIG_KEY: str = "max_batches"
_EVENT_EXPORTER_FILTER_KEYS: frozenset[str] = frozenset({"event_kinds", "min_severity"})
_EVENT_EXPORTER_KEYS: frozenset[str] = _EVENT_EXPORTER_FILTER_KEYS | frozenset({"named"})
_LEGACY_EVENT_EXPORTERS_CONFIG_KEY: str = "event_exporters"


def load_project_config(*, project_dir: Path) -> ProjectConfig:
    """Load project config from the given project directory."""

    file_path: Path = _resolve_project_config_path(project_dir=project_dir)
    payload: dict[str, object] = _load_config_mapping(file_path=file_path)
    if _LEGACY_EVENT_EXPORTERS_CONFIG_KEY in payload:
        raise ProjectConfigError(f"{file_path} event_exporters was replaced by sinks.lifecycle")

    name: str = _require_str(payload=payload, key="name", file_path=file_path)
    adapter: str = _require_str(payload=payload, key="adapter", file_path=file_path)
    default_target: str | None = _optional_str(payload=payload, key="default_target")
    connection: dict[str, object] = _optional_mapping(payload=payload, key="connection")
    connections: dict[str, dict[str, object]] = _load_connections(
        payload=payload.get("connections"), file_path=file_path
    )
    settings: SettingsConfig = _load_settings(payload=payload.get("settings"), file_path=file_path)
    scopes: ScopesConfig = _load_scopes(payload=payload.get("scopes"), file_path=file_path)
    cost: CostConfig = _load_cost(payload=payload.get("cost"), file_path=file_path)
    constants: ConstantsConfig = _load_constants(
        payload=payload.get("constants"), file_path=file_path
    )
    cursors: CursorsConfig = _load_cursors(payload=payload.get("cursors"), file_path=file_path)
    microbatches: MicrobatchesConfig = _load_microbatches(
        payload=payload.get("microbatches"), file_path=file_path
    )
    defaults: DefaultsConfig = _load_defaults(payload=payload.get("defaults"), file_path=file_path)
    materialization_defaults: MaterializationDefaultsConfig = _load_materialization_defaults(
        payload=payload.get("materialization_defaults"), file_path=file_path
    )
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
    sinks: SinksConfig = _load_sinks(payload=payload.get("sinks"), file_path=file_path)
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
        connections=connections,
        settings=settings,
        scopes=scopes,
        cost=cost,
        constants=constants,
        cursors=cursors,
        microbatches=microbatches,
        defaults=defaults,
        materialization_defaults=materialization_defaults,
        path_defaults=path_defaults,
        vars=vars_map,
        targets=targets,
        janitor=janitor,
        snapshots=snapshots,
        scenario=scenario,
        dbt=dbt,
        sinks=sinks,
    )


def _load_sinks(*, payload: object, file_path: Path) -> SinksConfig:
    if payload is None:
        return SinksConfig()
    if not isinstance(payload, dict):
        raise ProjectConfigError(f"{file_path} sinks must be a mapping")
    mapping: dict[str, object] = cast(dict[str, object], payload)
    _validate_allowed_keys(
        mapping=mapping,
        allowed_keys=frozenset({"lifecycle"}),
        label="sinks",
        file_path=file_path,
    )
    return SinksConfig(
        lifecycle=_load_lifecycle_sinks(
            payload=mapping.get("lifecycle"),
            file_path=file_path,
        )
    )


def _load_lifecycle_sinks(*, payload: object, file_path: Path) -> LifecycleEventSinksConfig:
    from sqlbuild.runtime.event_exporting.constants import (
        EVENT_EXPORT_KINDS,
        EVENT_EXPORT_SEVERITIES,
    )

    if payload is None:
        return LifecycleEventSinksConfig()
    if not isinstance(payload, dict):
        raise ProjectConfigError(f"{file_path} sinks.lifecycle must be a mapping")
    config_mapping: dict[str, object] = cast(dict[str, object], payload)
    _validate_allowed_keys(
        mapping=config_mapping,
        allowed_keys=_EVENT_EXPORTER_KEYS,
        label="sinks.lifecycle",
        file_path=file_path,
    )

    def load_filter(*, value: object, label: str) -> LifecycleEventSinkFilterConfig:
        if not isinstance(value, dict):
            raise ProjectConfigError(f"{file_path} {label} must be a mapping")
        filter_mapping: dict[str, object] = cast(dict[str, object], value)
        _validate_allowed_keys(
            mapping=filter_mapping,
            allowed_keys=_EVENT_EXPORTER_FILTER_KEYS,
            label=label,
            file_path=file_path,
        )
        kinds_value: object = filter_mapping.get("event_kinds")
        kinds: frozenset[str] | None = None
        if kinds_value is not None:
            if not isinstance(kinds_value, list) or not all(
                isinstance(kind, str) for kind in kinds_value
            ):
                raise ProjectConfigError(
                    f"{file_path} {label}.event_kinds must be a list of strings"
                )
            kinds = frozenset(cast(list[str], kinds_value))
            unknown: frozenset[str] = kinds - EVENT_EXPORT_KINDS
            if unknown:
                raise ProjectConfigError(
                    f"{file_path} {label}.event_kinds contains unknown kind(s): "
                    + ", ".join(sorted(unknown))
                )
        severity_value: object = filter_mapping.get("min_severity")
        severity: EventExportSeverity | None = None
        if severity_value is not None:
            if not isinstance(severity_value, str) or severity_value not in EVENT_EXPORT_SEVERITIES:
                raise ProjectConfigError(
                    f"{file_path} {label}.min_severity must be one of: "
                    + ", ".join(EVENT_EXPORT_SEVERITIES)
                )
            severity = EventExportSeverity(severity_value)
        return LifecycleEventSinkFilterConfig(event_kinds=kinds, min_severity=severity)

    named_value: object = config_mapping.get("named", {})
    if not isinstance(named_value, dict):
        raise ProjectConfigError(f"{file_path} sinks.lifecycle.named must be a mapping")
    named: dict[str, LifecycleEventSinkFilterConfig] = {}
    for name, value in named_value.items():
        if not isinstance(name, str) or not name:
            raise ProjectConfigError(f"{file_path} sinks.lifecycle.named contains an invalid name")
        named[name] = load_filter(value=value, label=f"sinks.lifecycle.named.{name}")
    defaults_mapping: dict[str, object] = {
        key: value for key, value in config_mapping.items() if key in _EVENT_EXPORTER_FILTER_KEYS
    }
    return LifecycleEventSinksConfig(
        defaults=load_filter(value=defaults_mapping, label="sinks.lifecycle"),
        named=named,
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
    connections: dict[str, dict[str, object]] = _load_connections(
        payload=payload.get("connections"), file_path=file_path
    )
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
        connections=connections,
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
    raw_column_contract_mode: object = mapping.get(
        "column_contract_mode", ColumnContractMode.IMPLICIT.value
    )
    try:
        column_contract_mode: ColumnContractMode = ColumnContractMode(raw_column_contract_mode)
    except (TypeError, ValueError) as error:
        raise ProjectConfigError(
            "settings.column_contract_mode must be one of: implicit, explicit"
        ) from error
    auto_load_sources: bool = _optional_bool(mapping=mapping, key="auto_load_sources", default=True)
    virtual_environments: bool = _optional_bool(
        mapping=mapping,
        key="virtual_environments",
        default=False,
    )
    changes_only: bool = _optional_bool(mapping=mapping, key="changes_only", default=False)
    microbatch_concurrency: bool = _optional_bool(
        mapping=mapping, key="microbatch_concurrency", default=False
    )
    microbatch_unaccounted_partition_policy: str = (
        _optional_str(payload=mapping, key="microbatch_unaccounted_partition_policy")
        or "synthesize"
    )
    valid_unaccounted_policies: frozenset[str] = frozenset(
        {"synthesize", "recover_empty", "recover_all"}
    )
    if microbatch_unaccounted_partition_policy not in valid_unaccounted_policies:
        raise ProjectConfigError(
            "settings.microbatch_unaccounted_partition_policy must be one of: "
            + ", ".join(sorted(valid_unaccounted_policies))
        )
    concurrency_key: str = (
        LEGACY_CONFIG_CONCURRENCY_KEY
        if LEGACY_CONFIG_CONCURRENCY_KEY in mapping
        else CONFIG_CONCURRENCY_KEY
    )
    concurrency: int = _optional_int(mapping=mapping, key=concurrency_key, default=1)
    if concurrency < 1:
        raise ProjectConfigError("settings.concurrency must be >= 1")
    table_promotion_mode: str | None = _optional_str(payload=mapping, key="table_promotion_mode")
    raw_default_audit_severity: str | None = _optional_str(
        payload=mapping, key="default_audit_severity"
    )
    default_audit_severity: AuditSeverity | None = None
    if raw_default_audit_severity is not None:
        try:
            default_audit_severity = AuditSeverity(raw_default_audit_severity)
        except ValueError as error:
            allowed: str = ", ".join(item.value for item in AuditSeverity)
            raise ProjectConfigError(
                f"settings.default_audit_severity must be one of: {allowed}"
            ) from error
    default_audit_run_scope: str | None = _optional_str(
        payload=mapping, key="default_audit_run_scope"
    )
    return SettingsConfig(
        sql_analysis=sql_analysis,
        query_change_tracking=query_change_tracking,
        sql_validation=sql_validation,
        column_contract_mode=column_contract_mode,
        concurrency=concurrency,
        auto_load_sources=auto_load_sources,
        changes_only=changes_only,
        virtual_environments=virtual_environments,
        microbatch_concurrency=microbatch_concurrency,
        microbatch_unaccounted_partition_policy=microbatch_unaccounted_partition_policy,
        table_promotion_mode=table_promotion_mode,
        default_audit_severity=default_audit_severity,
        default_audit_run_scope=default_audit_run_scope,
    )


def _load_cursors(*, payload: object, file_path: Path) -> CursorsConfig:
    mapping: dict[str, object] = _coerce_mapping(
        payload=payload, label="cursors", file_path=file_path
    )
    _validate_allowed_keys(
        mapping=mapping,
        allowed_keys=frozenset({"future", "start"}),
        label="cursors",
        file_path=file_path,
    )
    future: dict[str, object] = _coerce_mapping(
        payload=mapping.get("future"), label="cursors.future", file_path=file_path
    )
    _validate_allowed_keys(
        mapping=future,
        allowed_keys=frozenset({"max_distance", "action"}),
        label="cursors.future",
        file_path=file_path,
    )
    max_distance: str | None = _optional_str(payload=future, key="max_distance")
    if (
        max_distance is not None
        and max_distance != ZERO_DAY_CURSOR_DURATION
        and Duration.parse(max_distance) is None
    ):
        raise ProjectConfigError(
            "cursors.future.max_distance must be a duration like 0d, 7d, 12h, or 1mo"
        )
    raw_action: str | None = _optional_str(payload=future, key="action")
    try:
        action: FutureCursorAction = FutureCursorAction(raw_action or FutureCursorAction.ERROR)
    except ValueError:
        raise ProjectConfigError("cursors.future.action must be one of: cap, error") from None
    start: dict[str, object] = _coerce_mapping(
        payload=mapping.get("start"), label="cursors.start", file_path=file_path
    )
    _validate_allowed_keys(
        mapping=start,
        allowed_keys=frozenset({"max_ahead", "action"}),
        label="cursors.start",
        file_path=file_path,
    )
    max_ahead: str | None = _optional_str(payload=start, key="max_ahead")
    if (
        max_ahead is not None
        and max_ahead != ZERO_DAY_CURSOR_DURATION
        and Duration.parse(max_ahead) is None
    ):
        raise ProjectConfigError(
            "cursors.start.max_ahead must be a duration like 0d, 7d, 12h, or 1mo"
        )
    raw_start_action: str | None = _optional_str(payload=start, key="action")
    try:
        start_action: FutureCursorAction = FutureCursorAction(
            raw_start_action or FutureCursorAction.ERROR
        )
    except ValueError:
        raise ProjectConfigError("cursors.start.action must be one of: cap, error") from None
    return CursorsConfig(
        future=FutureCursorsConfig(max_distance=max_distance, action=action),
        start=StartCursorsConfig(max_ahead=max_ahead, action=start_action),
    )


def _load_microbatches(*, payload: object, file_path: Path) -> MicrobatchesConfig:
    mapping: dict[str, object] = _coerce_mapping(
        payload=payload, label="microbatches", file_path=file_path
    )
    _validate_allowed_keys(
        mapping=mapping,
        allowed_keys=frozenset({"limits"}),
        label="microbatches",
        file_path=file_path,
    )
    limits: dict[str, object] = _coerce_mapping(
        payload=mapping.get("limits"), label="microbatches.limits", file_path=file_path
    )
    _validate_allowed_keys(
        mapping=limits,
        allowed_keys=frozenset({_MAX_BATCHES_CONFIG_KEY, "action"}),
        label="microbatches.limits",
        file_path=file_path,
    )
    max_batches: int | None = None
    if _MAX_BATCHES_CONFIG_KEY in limits:
        if isinstance(limits[_MAX_BATCHES_CONFIG_KEY], bool):
            raise ProjectConfigError("microbatches.limits.max_batches must be a positive integer")
        max_batches = _optional_int(mapping=limits, key=_MAX_BATCHES_CONFIG_KEY, default=0)
        if max_batches < 1:
            raise ProjectConfigError("microbatches.limits.max_batches must be a positive integer")
    raw_action: str = _optional_str(payload=limits, key="action") or MicrobatchLimitAction.ERROR
    try:
        action: MicrobatchLimitAction = MicrobatchLimitAction(raw_action)
    except ValueError:
        raise ProjectConfigError("microbatches.limits.action must be one of: error, warn") from None
    if action not in {MicrobatchLimitAction.ERROR, MicrobatchLimitAction.WARN}:
        raise ProjectConfigError("microbatches.limits.action must be one of: error, warn")
    return MicrobatchesConfig(limits=MicrobatchLimitsConfig(max_batches=max_batches, action=action))


def _load_scopes(*, payload: object, file_path: Path) -> ScopesConfig:
    mapping: dict[str, object] = _coerce_mapping(
        payload=payload, label="scopes", file_path=file_path
    )
    _validate_allowed_keys(
        mapping=mapping,
        allowed_keys=frozenset({"enforce_placement"}),
        label="scopes",
        file_path=file_path,
    )
    return ScopesConfig(
        enforce_placement=_optional_bool(mapping=mapping, key="enforce_placement", default=True)
    )


def _load_cost(*, payload: object, file_path: Path) -> CostConfig:
    mapping: dict[str, object] = _coerce_mapping(payload=payload, label="cost", file_path=file_path)
    _validate_allowed_keys(
        mapping=mapping,
        allowed_keys=frozenset({USD_PER_CREDIT_CONFIG_KEY}),
        label="cost",
        file_path=file_path,
    )
    if USD_PER_CREDIT_CONFIG_KEY not in mapping:
        return CostConfig()
    raw_value: object = mapping[USD_PER_CREDIT_CONFIG_KEY]
    if isinstance(raw_value, bool) or not isinstance(raw_value, int | float):
        raise ProjectConfigError(f"{file_path} cost.usd_per_credit must be a number")
    value: Decimal = Decimal(str(raw_value))
    if not value.is_finite() or value <= 0:
        raise ProjectConfigError(
            f"{file_path} cost.usd_per_credit must be a finite number greater than zero"
        )
    return CostConfig(usd_per_credit=value, usd_per_credit_is_default=False)


def _load_constants(*, payload: object, file_path: Path) -> ConstantsConfig:
    mapping: dict[str, object] = _coerce_mapping(
        payload=payload, label="constants", file_path=file_path
    )
    key: str = "collection_rendering"
    _validate_allowed_keys(
        mapping=mapping,
        allowed_keys=frozenset({key}),
        label="constants",
        file_path=file_path,
    )
    raw_value: object = mapping.get(key, CollectionRendering.VALUE_LIST.value)
    if not isinstance(raw_value, str):
        raise ProjectConfigError(f"{file_path} constants.{key} must be a string")
    try:
        collection_rendering: CollectionRendering = CollectionRendering(raw_value)
    except ValueError as error:
        valid_values: str = ", ".join(rendering.value for rendering in CollectionRendering)
        raise ProjectConfigError(
            f"{file_path} constants.{key} must be one of: {valid_values}"
        ) from error
    return ConstantsConfig(collection_rendering=collection_rendering)


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
    unsupported_glob_parts_list: list[str] = []
    for part in path_parts:
        if part in GLOB_SEGMENTS:
            continue
        if any(marker in part for marker in UNSUPPORTED_GLOB_MARKERS):
            unsupported_glob_parts_list.append(part)
    unsupported_glob_parts: tuple[str, ...] = tuple(unsupported_glob_parts_list)
    if unsupported_glob_parts:
        unsupported: str = ", ".join(unsupported_glob_parts)
        raise ProjectConfigError(
            f"{file_path} path_defaults['{path_key}'] contains unsupported glob segment(s): "
            f"{unsupported}. Use '*' or '**' as complete path segments."
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
    merge_exclude_columns: tuple[str, ...] = tuple(
        _load_string_sequence(
            payload=mapping.get("merge_exclude_columns"),
            label="defaults.merge_exclude_columns",
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
        seed_database=_optional_str(payload=mapping, key="seed_database"),
        seed_schema=_optional_str(payload=mapping, key="seed_schema"),
        function_database=_optional_str(payload=mapping, key="function_database"),
        function_schema=_optional_str(payload=mapping, key="function_schema"),
        contract=_optional_contract_policy(mapping=mapping, key="contract"),
        incremental_strategy=_optional_str(payload=mapping, key="incremental_strategy"),
        incremental_mode=_optional_str(payload=mapping, key="incremental_mode"),
        microbatch_strategy=_optional_str(payload=mapping, key="microbatch_strategy"),
        cursor_watermark_mode=_optional_str(payload=mapping, key="cursor_watermark_mode"),
        merge_exclude_columns=merge_exclude_columns,
        full_refresh=_optional_nullable_bool(mapping=mapping, key="full_refresh"),
        append_cursor_inclusive=_optional_templated_bool(
            mapping=mapping,
            key="append_cursor_inclusive",
        ),
        cursor_start=_optional_cursor_start(mapping=mapping, key="cursor_start"),
        cursor_end=_optional_cursor_start(mapping=mapping, key="cursor_end"),
        cursor_start_max_ahead=_optional_str(payload=mapping, key="cursor_start_max_ahead"),
        cursor_start_max_action=_optional_str(payload=mapping, key="cursor_start_max_action"),
        cursor_future_max_distance=_optional_str(payload=mapping, key="cursor_future_max_distance"),
        cursor_future_action=_optional_str(payload=mapping, key="cursor_future_action"),
        lookback=_optional_str(payload=mapping, key="lookback"),
        batch_size=_optional_scalar_batch_size(mapping=mapping, key="batch_size"),
        batch_concurrency=(
            _optional_int(mapping=mapping, key=_BATCH_CONCURRENCY_CONFIG_KEY, default=1)
            if _BATCH_CONCURRENCY_CONFIG_KEY in mapping
            else None
        ),
        max_microbatches=(
            _optional_int(mapping=mapping, key=MAX_MICROBATCHES_CONFIG_KEY, default=1)
            if MAX_MICROBATCHES_CONFIG_KEY in mapping
            else None
        ),
        unaccounted_partition_policy=_optional_str(
            payload=mapping, key="unaccounted_partition_policy"
        ),
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


def _load_materialization_defaults(
    *, payload: object, file_path: Path
) -> MaterializationDefaultsConfig:
    mapping: dict[str, object] = _coerce_mapping(
        payload=payload, label="materialization_defaults", file_path=file_path
    )
    materializations: tuple[str, ...] = TIME_TRAVEL_RETENTION_MATERIALIZATIONS
    _validate_allowed_keys(
        mapping=mapping,
        allowed_keys=frozenset(materializations),
        label="materialization_defaults",
        file_path=file_path,
    )
    loaded: dict[str, MaterializationRetentionDefaults] = {}
    for materialization in materializations:
        materialization_mapping: dict[str, object] = _coerce_mapping(
            payload=mapping.get(materialization),
            label=f"materialization_defaults.{materialization}",
            file_path=file_path,
        )
        _validate_allowed_keys(
            mapping=materialization_mapping,
            allowed_keys=frozenset({"time_travel_retention", "table_type"}),
            label=f"materialization_defaults.{materialization}",
            file_path=file_path,
        )
        loaded[materialization] = MaterializationRetentionDefaults(
            time_travel_retention=_optional_retention_policy(
                mapping=materialization_mapping,
                key="time_travel_retention",
                label=f"materialization_defaults.{materialization}.time_travel_retention",
                file_path=file_path,
                allow_inherit=True,
            ),
            table_type=_optional_table_type(
                mapping=materialization_mapping,
                key="table_type",
                label=f"materialization_defaults.{materialization}.table_type",
                file_path=file_path,
                allow_inherit=True,
            ),
        )
    return MaterializationDefaultsConfig(**loaded)


def _optional_retention_policy(
    *,
    mapping: dict[str, object],
    key: str,
    label: str,
    file_path: Path,
    allow_inherit: bool = False,
) -> AuthoredTimeTravelRetention | None:
    value: object | None = mapping.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ProjectConfigError(f"{file_path} {label} must be a whole-day string like '7d'")
    if allow_inherit and value == TimeTravelRetentionValue.INHERIT:
        return None
    if value == TimeTravelRetentionValue.DISABLED:
        return AuthoredTimeTravelRetention(unmanaged=True)
    if value == ZERO_DAY_CURSOR_DURATION:
        return AuthoredTimeTravelRetention(desired_days=0)
    duration: Duration | None = Duration.parse(value)
    if duration is None or duration.units != frozenset({DURATION_DAY_UNIT}):
        allowed_keywords: str = ", 'inherit', or 'disabled'" if allow_inherit else " or 'disabled'"
        raise ProjectConfigError(
            f"{file_path} {label} must be a whole-day string like '7d'{allowed_keywords}"
        )
    return AuthoredTimeTravelRetention(desired_days=duration.days)


def _optional_table_type(
    *,
    mapping: dict[str, object],
    key: str,
    label: str,
    file_path: Path,
    allow_inherit: bool = False,
) -> TableType | None:
    value: object | None = mapping.get(key)
    if value is None or allow_inherit and value == TableTypeValue.INHERIT:
        return None
    try:
        return TableType(value)
    except (TypeError, ValueError) as exc:
        suffix: str = ", or 'inherit'" if allow_inherit else ""
        raise ProjectConfigError(
            f"{file_path} {label} must be 'permanent' or 'transient'{suffix}"
        ) from exc


def _optional_table_type_downgrade_policy(
    *, mapping: dict[str, object], key: str, label: str, file_path: Path
) -> TableTypeDowngradePolicy | None:
    value: object | None = mapping.get(key)
    if value is None:
        return None
    try:
        return TableTypeDowngradePolicy(value)
    except (TypeError, ValueError) as exc:
        raise ProjectConfigError(
            f"{file_path} {label} must be 'deny', 'require_confirmation', or 'allow'"
        ) from exc


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
        _validate_target_keys(
            target_mapping=target_mapping, target_name=target_name, file_path=file_path
        )
        clone_mapping: dict[str, object] = _coerce_mapping(
            payload=target_mapping.get("clone"),
            label=f"targets.{target_name}.clone",
            file_path=file_path,
        )
        _validate_clone_keys(
            clone_mapping=clone_mapping, target_name=target_name, file_path=file_path
        )
        state_mapping: dict[str, object] = _coerce_mapping(
            payload=target_mapping.get("state"),
            label=f"targets.{target_name}.state",
            file_path=file_path,
        )
        _validate_state_keys(
            state_mapping=state_mapping, target_name=target_name, file_path=file_path
        )
        connection, connection_name = _load_target_connection(
            target_mapping=target_mapping, target_name=target_name, file_path=file_path
        )
        targets[target_name] = TargetConfig(
            connection=connection,
            connection_name=connection_name,
            vars=_load_string_mapping(payload=target_mapping.get("vars"), file_path=file_path),
            database=_optional_str(payload=target_mapping, key="database"),
            schema=_optional_str(payload=target_mapping, key="schema"),
            loader_schema=_optional_str(payload=target_mapping, key="loader_schema"),
            defer_sources_to=_optional_str(payload=target_mapping, key="defer_sources_to"),
            defer_clone_from=_optional_str(payload=target_mapping, key="defer_clone_from"),
            changes_only=_optional_nullable_bool(mapping=target_mapping, key="changes_only"),
            compile_cache=_optional_nullable_bool(mapping=target_mapping, key="compile_cache"),
            time_travel_retention=_optional_retention_policy(
                mapping=target_mapping,
                key="time_travel_retention",
                label=f"targets.{target_name}.time_travel_retention",
                file_path=file_path,
            ),
            owns_time_travel_retention_namespace=_optional_bool(
                mapping=target_mapping,
                key="owns_time_travel_retention_namespace",
                default=False,
            ),
            default_table_type=_optional_table_type(
                mapping=target_mapping,
                key="default_table_type",
                label=f"targets.{target_name}.default_table_type",
                file_path=file_path,
            ),
            table_type_downgrade=(
                _optional_table_type_downgrade_policy(
                    mapping=target_mapping,
                    key="table_type_downgrade",
                    label=f"targets.{target_name}.table_type_downgrade",
                    file_path=file_path,
                )
                or TableTypeDowngradePolicy.REQUIRE_CONFIRMATION
            ),
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
        _validate_target_keys(
            target_mapping=target_mapping, target_name=target_name, file_path=file_path
        )
        clone_mapping: dict[str, object] = _coerce_mapping(
            payload=target_mapping.get("clone"),
            label=f"targets.{target_name}.clone",
            file_path=file_path,
        )
        _validate_clone_keys(
            clone_mapping=clone_mapping, target_name=target_name, file_path=file_path
        )
        state_mapping: dict[str, object] = _coerce_mapping(
            payload=target_mapping.get("state"),
            label=f"targets.{target_name}.state",
            file_path=file_path,
        )
        _validate_state_keys(
            state_mapping=state_mapping, target_name=target_name, file_path=file_path
        )
        connection, connection_name = _load_target_connection(
            target_mapping=target_mapping, target_name=target_name, file_path=file_path
        )
        targets[target_name] = LocalTargetConfig(
            connection=connection,
            connection_name=connection_name,
            vars=_load_string_mapping(payload=target_mapping.get("vars"), file_path=file_path),
            database=_optional_str(payload=target_mapping, key="database"),
            schema=_optional_str(payload=target_mapping, key="schema"),
            loader_schema=_optional_str(payload=target_mapping, key="loader_schema"),
            defer_sources_to=_optional_str(payload=target_mapping, key="defer_sources_to"),
            defer_clone_from=_optional_str(payload=target_mapping, key="defer_clone_from"),
            changes_only=_optional_nullable_bool(mapping=target_mapping, key="changes_only"),
            compile_cache=_optional_nullable_bool(mapping=target_mapping, key="compile_cache"),
            time_travel_retention=_optional_retention_policy(
                mapping=target_mapping,
                key="time_travel_retention",
                label=f"targets.{target_name}.time_travel_retention",
                file_path=file_path,
            ),
            owns_time_travel_retention_namespace=_optional_nullable_bool(
                mapping=target_mapping,
                key="owns_time_travel_retention_namespace",
            ),
            default_table_type=_optional_table_type(
                mapping=target_mapping,
                key="default_table_type",
                label=f"targets.{target_name}.default_table_type",
                file_path=file_path,
            ),
            table_type_downgrade=_optional_table_type_downgrade_policy(
                mapping=target_mapping,
                key="table_type_downgrade",
                label=f"targets.{target_name}.table_type_downgrade",
                file_path=file_path,
            ),
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


def _load_connections(*, payload: object, file_path: Path) -> dict[str, dict[str, object]]:
    mapping: dict[str, object] = _coerce_mapping(
        payload=payload, label="connections", file_path=file_path
    )
    connections: dict[str, dict[str, object]] = {}
    for name, value in mapping.items():
        if not name.strip():
            raise ProjectConfigError(f"{file_path} connections contains an empty name")
        connections[name] = dict(
            _coerce_mapping(payload=value, label=f"connections.{name}", file_path=file_path)
        )
    return connections


def _load_target_connection(
    *, target_mapping: dict[str, object], target_name: str, file_path: Path
) -> tuple[dict[str, object], str | None]:
    value: object | None = target_mapping.get("connection")
    if value is None:
        return {}, None
    if isinstance(value, dict):
        return cast(dict[str, object], value), None
    if isinstance(value, str) and value.strip():
        return {}, value.strip()
    raise ProjectConfigError(
        f"{file_path} targets.{target_name}.connection must be a non-empty string or mapping"
    )


def _validate_target_keys(
    *, target_mapping: dict[str, object], target_name: str, file_path: Path
) -> None:
    _validate_allowed_keys(
        mapping=target_mapping,
        allowed_keys=frozenset(
            {
                "connection",
                "vars",
                "database",
                "schema",
                "loader_schema",
                "defer_sources_to",
                "defer_clone_from",
                "changes_only",
                "compile_cache",
                "time_travel_retention",
                "owns_time_travel_retention_namespace",
                "default_table_type",
                "table_type_downgrade",
                "clone",
                "state",
            }
        ),
        label=f"targets.{target_name}",
        file_path=file_path,
    )


def _validate_clone_keys(
    *, clone_mapping: dict[str, object], target_name: str, file_path: Path
) -> None:
    _validate_allowed_keys(
        mapping=clone_mapping,
        allowed_keys=frozenset({"allow_as_clone_origin", "allow_as_clone_destination"}),
        label=f"targets.{target_name}.clone",
        file_path=file_path,
    )


def _validate_state_keys(
    *, state_mapping: dict[str, object], target_name: str, file_path: Path
) -> None:
    _validate_allowed_keys(
        mapping=state_mapping,
        allowed_keys=frozenset(
            {"backend", "schema", "connection", "allow_reset", "unsuffixed_virtual_env"}
        ),
        label=f"targets.{target_name}.state",
        file_path=file_path,
    )


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
    reuse_keys: tuple[str, ...] = tuple(
        key
        for key in (DBT_LEGACY_REUSE_FROM_CONFIG_KEY, DBT_PRODUCTION_REF_CONFIG_KEY)
        if key in mapping
    )
    if reuse_keys:
        raise ProjectConfigError(
            f"{file_path} [dbt] reuse option(s) were removed: {', '.join(reuse_keys)}; "
            "dbt production-ref reuse is no longer supported"
        )
    removed_keys: tuple[str, ...] = tuple(
        key
        for key in (DBT_DEFER_CLONE_CONFIG_KEY, DBT_REPLAY_ON_CHANGE_CONFIG_KEY)
        if key in mapping
    )
    if removed_keys:
        raise ProjectConfigError(
            f"{file_path} [dbt] option(s) were removed: {', '.join(removed_keys)}; "
            "use dbt-native --state/--defer"
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
    )


def _load_local_dbt(*, payload: object, file_path: Path) -> LocalDbtConfig:
    """Load optional local dbt interop configuration."""

    mapping: dict[str, object] = _coerce_mapping(payload=payload, label="dbt", file_path=file_path)
    if DBT_DEFER_CLONE_CONFIG_KEY in mapping:
        raise ProjectConfigError(
            f"{file_path} [dbt].defer_clone_from was removed; use dbt-native --state/--defer"
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
