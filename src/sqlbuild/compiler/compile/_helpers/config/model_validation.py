"""Compile-time validation of model config combinations."""

from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from sqlbuild.compiler.compile.constants import SQL_WILDCARD_TOKEN
from sqlbuild.compiler.compile.exceptions import CompileInputError
from sqlbuild.compiler.compile.models import CompileModelConfig
from sqlbuild.compiler.planner.types import (
    ContractPolicy,
    CursorGrain,
    CursorType,
    HistoricalInput,
    IncrementalMode,
    IncrementalStrategy,
    InitialValidFrom,
    MaterializationType,
    SnapshotFullRefreshPolicy,
    SnapshotSchemaChangePolicy,
    SnapshotStrategy,
)
from sqlbuild.spec.contracts.constants import CURSOR_POLICY_DISABLED, ZERO_DAY_CURSOR_DURATION
from sqlbuild.spec.contracts.models import (
    ResolvedTimeTravelRetention,
    SchemaColumn,
    SettingsConfig,
)
from sqlbuild.spec.contracts.types import FutureCursorAction

_VALID_STRATEGIES: frozenset[str] = frozenset(s.value for s in IncrementalStrategy)
_VALID_CURSOR_TYPES: frozenset[str] = frozenset(ct.value for ct in CursorType)
_VALID_CURSOR_GRAINS: frozenset[str] = frozenset(cg.value for cg in CursorGrain)
_VALID_INCREMENTAL_MODES: frozenset[str] = frozenset(m.value for m in IncrementalMode)
_VALID_CONTRACT_POLICIES: frozenset[str] = frozenset(p.value for p in ContractPolicy)
_VALID_SNAPSHOT_STRATEGIES: frozenset[str] = frozenset(s.value for s in SnapshotStrategy)
_VALID_HISTORICAL_INPUTS: frozenset[str] = frozenset(h.value for h in HistoricalInput)
_VALID_INITIAL_VALID_FROM: frozenset[str] = frozenset(v.value for v in InitialValidFrom)
_VALID_SNAPSHOT_FULL_REFRESH_POLICIES: frozenset[str] = frozenset(
    p.value for p in SnapshotFullRefreshPolicy
)
_VALID_SNAPSHOT_SCHEMA_CHANGE_POLICIES: frozenset[str] = frozenset(
    p.value for p in SnapshotSchemaChangePolicy
)
_BUILTIN_MATERIALIZATION_TYPES: frozenset[str] = frozenset(
    (
        MaterializationType.VIEW,
        MaterializationType.TABLE,
        MaterializationType.INCREMENTAL,
        MaterializationType.SNAPSHOT,
    )
)
_INCREMENTAL_ONLY_KEYS: tuple[str, ...] = (
    "on_schema_change",
    "replay_on_change",
    "append_cursor_inclusive",
    "merge_exclude_columns",
    "full_refresh",
)
_SNAPSHOT_DISALLOWED_KEYS: tuple[str, ...] = (
    "incremental_strategy",
    "incremental_mode",
    "append_cursor_inclusive",
    "batch_size",
    "cursor",
    "cursor_type",
    "cursor_grain",
    "cursor_inputs",
    "cursor_filter_inputs",
    "cursor_watermark_inputs",
    "lookback",
)
_CUSTOM_MATERIALIZATION_DISALLOWED_KEYS: tuple[str, ...] = (
    "on_schema_change",
    "incremental_strategy",
    "incremental_mode",
    "append_cursor_inclusive",
    "batch_size",
    "cursor",
    "cursor_type",
    "cursor_grain",
    "cursor_inputs",
    "cursor_filter_inputs",
    "cursor_watermark_inputs",
    "lookback",
)


def validate_incremental_config(
    *,
    config: CompileModelConfig,
    model_name: str,
    ref_count: int,
    known_input_names: frozenset[str],
    declared_columns: tuple[SchemaColumn, ...] | None = None,
) -> None:
    """Validate incremental model config rules after layering."""

    materialized: str | None = _str(config=config, key="materialized")
    if materialized in {MaterializationType.TABLE, MaterializationType.VIEW}:
        cursor_field: str
        for cursor_field in (
            "cursor_inputs",
            "cursor_filter_inputs",
            "cursor_watermark_inputs",
        ):
            if config.values.get(cursor_field) is not None:
                raise CompileInputError(
                    f"model '{model_name}': {cursor_field} requires cursor-based incremental "
                    "materialization"
                )
    if materialized != MaterializationType.INCREMENTAL:
        return

    strategy: str | None = _str(config=config, key="incremental_strategy")
    cursor: str | None = _str(config=config, key="cursor")
    cursor_type: str | None = _str(config=config, key="cursor_type")
    cursor_start: object | None = config.values.get("cursor_start")
    cursor_start_max_ahead: object | None = config.values.get("cursor_start_max_ahead")
    cursor_start_max_action: object | None = config.values.get("cursor_start_max_action")
    cursor_future_max_distance: object | None = config.values.get("cursor_future_max_distance")
    cursor_future_action: object | None = config.values.get("cursor_future_action")
    append_cursor_inclusive: object | None = config.values.get("append_cursor_inclusive")
    unique_key: object | None = config.values.get("unique_key")
    has_unique_key: bool = unique_key is not None and unique_key != () and unique_key != []
    lookback: str | None = _str(config=config, key="lookback")
    incremental_mode: str | None = _str(config=config, key="incremental_mode")
    batch_size: object | None = config.values.get("batch_size")
    batch_concurrency: object | None = config.values.get("batch_concurrency")
    unaccounted_partition_policy: object | None = config.values.get("unaccounted_partition_policy")
    legacy_cursor_inputs: object | None = config.values.get("cursor_inputs")
    cursor_filter_inputs: object | None = config.values.get("cursor_filter_inputs")
    cursor_watermark_inputs: object | None = config.values.get("cursor_watermark_inputs")
    cursor_grain: str | None = _str(config=config, key="cursor_grain")
    replay_on_change: object | None = config.values.get("replay_on_change")
    merge_exclude_columns: object | None = config.values.get("merge_exclude_columns")
    full_refresh: object | None = config.values.get("full_refresh")
    if replay_on_change is not None and not isinstance(replay_on_change, str):
        raise CompileInputError(f"model '{model_name}': replay_on_change must be a string")
    if strategy is None:
        raise CompileInputError(
            f"model '{model_name}': incremental materialization requires incremental_strategy"
        )
    if strategy not in _VALID_STRATEGIES:
        raise CompileInputError(
            f"model '{model_name}': unknown incremental_strategy '{strategy}'; "
            f"valid values: {', '.join(sorted(_VALID_STRATEGIES))}"
        )

    _validate_incremental_cursor_rules(
        model_name=model_name,
        cursor=cursor,
        cursor_type=cursor_type,
        cursor_grain=cursor_grain,
        cursor_start=cursor_start,
        append_cursor_inclusive=append_cursor_inclusive,
        strategy=strategy,
    )
    _validate_cursor_safety_overrides(
        model_name=model_name,
        cursor=cursor,
        cursor_start_max_ahead=cursor_start_max_ahead,
        cursor_start_max_action=cursor_start_max_action,
        cursor_future_max_distance=cursor_future_max_distance,
        cursor_future_action=cursor_future_action,
    )

    _validate_cursor_input_config(
        model_name=model_name,
        cursor=cursor,
        ref_count=ref_count,
        known_input_names=known_input_names,
        legacy_cursor_inputs=legacy_cursor_inputs,
        cursor_filter_inputs=cursor_filter_inputs,
        cursor_watermark_inputs=cursor_watermark_inputs,
    )

    if strategy == IncrementalStrategy.DELETE_INSERT and cursor is None and not has_unique_key:
        raise CompileInputError(
            f"model '{model_name}': delete_insert without cursor requires unique_key"
        )
    if strategy == IncrementalStrategy.MERGE and not has_unique_key:
        raise CompileInputError(f"model '{model_name}': merge strategy requires unique_key")
    if merge_exclude_columns is not None:
        excluded_columns: tuple[str, ...] = _validated_string_sequence(
            value=merge_exclude_columns,
            config_key="merge_exclude_columns",
            model_name=model_name,
        )
        if strategy != IncrementalStrategy.MERGE:
            raise CompileInputError(
                f"model '{model_name}': merge_exclude_columns requires incremental_strategy=merge"
            )
        if len({column.lower() for column in excluded_columns}) != len(excluded_columns):
            raise CompileInputError(
                f"model '{model_name}': merge_exclude_columns contains duplicate columns"
            )
        unique_key_columns: frozenset[str] = frozenset(
            column.lower() for column in _string_sequence(unique_key)
        )
        overlap: tuple[str, ...] = tuple(
            column for column in excluded_columns if column.lower() in unique_key_columns
        )
        if overlap:
            raise CompileInputError(
                f"model '{model_name}': merge_exclude_columns cannot include unique_key "
                f"column(s): {', '.join(overlap)}"
            )
    if full_refresh is not None and not isinstance(full_refresh, bool):
        raise CompileInputError(f"model '{model_name}': full_refresh must be a boolean")

    declared_column_names: frozenset[str] | None = _contract_declared_column_names(
        config=config,
        declared_columns=declared_columns,
    )
    if declared_column_names is not None:
        if cursor is not None:
            _validate_declared_config_column(
                column_name=cursor,
                config_key="cursor",
                declared_column_names=declared_column_names,
                model_name=model_name,
            )
        _validate_declared_config_columns(
            column_names=_string_sequence(unique_key),
            config_key="unique_key",
            declared_column_names=declared_column_names,
            model_name=model_name,
        )
        _validate_declared_config_columns(
            column_names=_string_sequence(merge_exclude_columns),
            config_key="merge_exclude_columns",
            declared_column_names=declared_column_names,
            model_name=model_name,
        )

    if lookback is not None and cursor is None:
        raise CompileInputError(
            f"model '{model_name}': lookback is only valid with cursor-based incremental"
        )

    if incremental_mode is not None and incremental_mode not in _VALID_INCREMENTAL_MODES:
        raise CompileInputError(
            f"model '{model_name}': unknown incremental_mode '{incremental_mode}'; "
            f"valid values: {', '.join(sorted(_VALID_INCREMENTAL_MODES))}"
        )
    if batch_size is not None and incremental_mode != IncrementalMode.MICROBATCH:
        raise CompileInputError(
            f"model '{model_name}': batch_size is only valid with incremental_mode=microbatch"
        )
    _validate_microbatch_state_config(
        model_name=model_name,
        strategy=strategy,
        incremental_mode=incremental_mode,
        batch_concurrency=batch_concurrency,
        unaccounted_partition_policy=unaccounted_partition_policy,
    )


def _validate_cursor_input_config(
    *,
    model_name: str,
    cursor: str | None,
    ref_count: int,
    known_input_names: frozenset[str],
    legacy_cursor_inputs: object | None,
    cursor_filter_inputs: object | None,
    cursor_watermark_inputs: object | None,
) -> None:
    """Validate cursor filter, watermark, and deprecated alias combinations."""

    if legacy_cursor_inputs is not None and cursor_filter_inputs is not None:
        raise CompileInputError(
            f"model '{model_name}': cursor_inputs is the deprecated name for "
            "cursor_filter_inputs and both cannot be declared"
        )
    filter_inputs: object | None = (
        cursor_filter_inputs if cursor_filter_inputs is not None else legacy_cursor_inputs
    )
    cursor_field: str
    cursor_value: object
    for cursor_field, cursor_value in (
        ("cursor_inputs", legacy_cursor_inputs),
        ("cursor_filter_inputs", cursor_filter_inputs),
        ("cursor_watermark_inputs", cursor_watermark_inputs),
    ):
        if cursor_value is not None and cursor is None:
            raise CompileInputError(f"model '{model_name}': {cursor_field} requires cursor")
        if cursor_value is not None:
            _validate_cursor_input_map(
                model_name=model_name,
                config_field=cursor_field,
                value=cursor_value,
            )
    if cursor_watermark_inputs is not None and filter_inputs is None:
        raise CompileInputError(
            f"model '{model_name}': cursor_watermark_inputs requires cursor_filter_inputs "
            "or deprecated cursor_inputs"
        )
    if isinstance(filter_inputs, dict):
        input_name: object
        filter_field: str = (
            "cursor_filter_inputs" if cursor_filter_inputs is not None else "cursor_inputs"
        )
        for input_name in filter_inputs:
            if str(input_name) not in known_input_names:
                expected_names: str = ", ".join(sorted(known_input_names))
                raise CompileInputError(
                    f"model '{model_name}': {filter_field} references unknown input "
                    f"'{input_name}'; expected one of: {expected_names}"
                )
    if cursor is not None and ref_count > 1 and filter_inputs is None:
        raise CompileInputError(
            f"model '{model_name}': models with cursor and multiple inputs require explicit "
            "cursor_inputs (deprecated) or cursor_filter_inputs"
        )


def _validate_cursor_input_map(*, model_name: str, config_field: str, value: object) -> None:
    """Validate one cursor input field as a relation-to-column map."""

    if not isinstance(value, dict):
        raise CompileInputError(f"model '{model_name}': {config_field} must be a relation map")
    if not value:
        raise CompileInputError(f"model '{model_name}': {config_field} must not be empty")
    relation_name: object
    cursor_column: object
    for relation_name, cursor_column in value.items():
        if not isinstance(relation_name, str) or not relation_name.strip():
            raise CompileInputError(
                f"model '{model_name}': {config_field} relation names must be non-empty strings"
            )
        if not isinstance(cursor_column, str) or not cursor_column.strip():
            raise CompileInputError(
                f"model '{model_name}': {config_field} column for relation "
                f"'{relation_name}' must be a non-empty string"
            )


def _validate_microbatch_state_config(
    *,
    model_name: str,
    strategy: str,
    incremental_mode: str | None,
    batch_concurrency: object | None,
    unaccounted_partition_policy: object | None,
) -> None:
    if batch_concurrency is not None:
        if isinstance(batch_concurrency, bool) or not isinstance(batch_concurrency, int):
            raise CompileInputError(
                f"model '{model_name}': batch_concurrency must be a positive integer"
            )
        if batch_concurrency <= 0:
            raise CompileInputError(
                f"model '{model_name}': batch_concurrency must be a positive integer"
            )
        if batch_concurrency > 1 and incremental_mode != IncrementalMode.MICROBATCH:
            raise CompileInputError(
                f"model '{model_name}': batch_concurrency > 1 requires incremental_mode=microbatch"
            )
        if batch_concurrency > 1 and strategy != IncrementalStrategy.DELETE_INSERT:
            raise CompileInputError(
                f"model '{model_name}': batch_concurrency > 1 requires "
                "incremental_strategy=delete_insert"
            )
    if unaccounted_partition_policy is None:
        return
    valid_policies: frozenset[str] = frozenset({"synthesize", "recover_empty", "recover_all"})
    if (
        not isinstance(unaccounted_partition_policy, str)
        or unaccounted_partition_policy not in valid_policies
    ):
        raise CompileInputError(
            f"model '{model_name}': unaccounted_partition_policy must be one of: "
            + ", ".join(sorted(valid_policies))
        )
    if incremental_mode != IncrementalMode.MICROBATCH:
        raise CompileInputError(
            f"model '{model_name}': unaccounted_partition_policy requires "
            "incremental_mode=microbatch"
        )


def validate_microbatch_project_capability(
    *, config: CompileModelConfig, settings: SettingsConfig, model_name: str
) -> None:
    """Require the project capability for a model concurrency ceiling above one."""

    batch_concurrency: object | None = config.values.get("batch_concurrency")
    if (
        isinstance(batch_concurrency, int)
        and not isinstance(batch_concurrency, bool)
        and batch_concurrency > 1
        and not settings.microbatch_concurrency
    ):
        raise CompileInputError(
            f"model '{model_name}': batch_concurrency > 1 requires "
            "settings.microbatch_concurrency = true"
        )


def _validate_incremental_cursor_rules(
    *,
    model_name: str,
    cursor: str | None,
    cursor_type: str | None,
    cursor_grain: str | None,
    cursor_start: object | None,
    append_cursor_inclusive: object | None,
    strategy: str | None,
) -> None:
    if cursor is not None and cursor_type is None:
        raise CompileInputError(
            f"model '{model_name}': cursor requires cursor_type "
            f"(valid values: {', '.join(sorted(_VALID_CURSOR_TYPES))})"
        )
    if cursor_type is not None and cursor_type not in _VALID_CURSOR_TYPES:
        raise CompileInputError(
            f"model '{model_name}': unknown cursor_type '{cursor_type}'; "
            f"valid values: {', '.join(sorted(_VALID_CURSOR_TYPES))}"
        )
    if cursor_grain is not None and cursor_type != CursorType.TIMESTAMP:
        raise CompileInputError(
            f"model '{model_name}': cursor_grain is only valid with cursor_type=timestamp"
        )
    if cursor_grain is not None and cursor_grain not in _VALID_CURSOR_GRAINS:
        raise CompileInputError(
            f"model '{model_name}': unknown cursor_grain '{cursor_grain}'; "
            f"valid values: {', '.join(sorted(_VALID_CURSOR_GRAINS))}"
        )
    if cursor is not None and cursor_type == CursorType.TIMESTAMP and cursor_grain is None:
        raise CompileInputError(
            f"model '{model_name}': cursor_type=timestamp requires cursor_grain "
            f"(valid values: {', '.join(sorted(_VALID_CURSOR_GRAINS))})"
        )
    if cursor_start is not None and cursor is None:
        raise CompileInputError(f"model '{model_name}': cursor_start requires cursor")
    if cursor_start is not None and cursor_type is None:
        raise CompileInputError(f"model '{model_name}': cursor_start requires cursor_type")
    if cursor_start is not None and cursor_type == CursorType.TIMESTAMP:
        _validate_timestamp_cursor_start(cursor_start=cursor_start, model_name=model_name)
    if cursor_start is not None and cursor_type == CursorType.INTEGER:
        _validate_integer_cursor_start(cursor_start=cursor_start, model_name=model_name)
    if append_cursor_inclusive is not None and not isinstance(append_cursor_inclusive, bool):
        raise CompileInputError(f"model '{model_name}': append_cursor_inclusive must be a boolean")
    if append_cursor_inclusive is not None and strategy != IncrementalStrategy.APPEND:
        raise CompileInputError(
            f"model '{model_name}': append_cursor_inclusive is only valid with append strategy"
        )
    if append_cursor_inclusive is not None and cursor is None:
        raise CompileInputError(f"model '{model_name}': append_cursor_inclusive requires cursor")


def _validate_cursor_safety_overrides(
    *,
    model_name: str,
    cursor: str | None,
    cursor_start_max_ahead: object | None,
    cursor_start_max_action: object | None,
    cursor_future_max_distance: object | None,
    cursor_future_action: object | None,
) -> None:
    values: tuple[object | None, ...] = (
        cursor_start_max_ahead,
        cursor_start_max_action,
        cursor_future_max_distance,
        cursor_future_action,
    )
    if cursor is None and any(value is not None for value in values):
        raise CompileInputError(f"model '{model_name}': cursor safety overrides require cursor")
    duration_pattern: re.Pattern[str] = re.compile(
        r"^(?=.*[1-9])(?:(\d+)y)?(?:(\d+)mo)?(?:(\d+)d)?(?:(\d+)h)?(?:(\d+)m)?(?:(\d+)s)?$"
    )
    if cursor_start_max_ahead is not None and (
        not isinstance(cursor_start_max_ahead, str)
        or (
            cursor_start_max_ahead not in {CURSOR_POLICY_DISABLED, ZERO_DAY_CURSOR_DURATION}
            and duration_pattern.fullmatch(cursor_start_max_ahead) is None
        )
    ):
        raise CompileInputError(
            f"model '{model_name}': cursor_start_max_ahead must be a duration or 'disabled'"
        )
    if cursor_future_max_distance is not None and (
        not isinstance(cursor_future_max_distance, str)
        or (
            cursor_future_max_distance != CURSOR_POLICY_DISABLED
            and duration_pattern.fullmatch(cursor_future_max_distance) is None
        )
    ):
        raise CompileInputError(
            f"model '{model_name}': cursor_future_max_distance must be a duration or 'disabled'"
        )
    for key, value in (
        ("cursor_start_max_action", cursor_start_max_action),
        ("cursor_future_action", cursor_future_action),
    ):
        if value is not None and value not in set(FutureCursorAction):
            raise CompileInputError(f"model '{model_name}': {key} must be one of: cap, error")


def validate_contract_config(
    *,
    config: CompileModelConfig,
    model_name: str,
) -> None:
    """Validate model contract config values after layering."""

    raw_contract: object | None = config.values.get("contract")
    if raw_contract is None:
        return
    if not isinstance(raw_contract, str):
        raise CompileInputError(f"model '{model_name}': contract must be a string")
    contract: str = raw_contract
    if contract not in _VALID_CONTRACT_POLICIES:
        raise CompileInputError(
            f"model '{model_name}': unknown contract '{contract}'; valid values: "
            f"{', '.join(sorted(_VALID_CONTRACT_POLICIES))}"
        )


def validate_non_incremental_config(
    *,
    config: CompileModelConfig,
    model_name: str,
) -> None:
    """Reject incremental-only config keys on non-incremental models."""

    materialized: str | None = _str(config=config, key="materialized")
    if materialized == MaterializationType.INCREMENTAL:
        return

    key: str
    for key in _INCREMENTAL_ONLY_KEYS:
        if config.values.get(key) is not None:
            raise CompileInputError(
                f"model '{model_name}': {key} is only valid for incremental models"
            )


def validate_snapshot_config(
    *,
    config: CompileModelConfig,
    model_name: str,
    declared_columns: tuple[SchemaColumn, ...] | None = None,
) -> None:
    """Validate snapshot model config combinations after layering."""

    materialized: str | None = _str(config=config, key="materialized")
    if materialized != MaterializationType.SNAPSHOT:
        return

    strategy: str | None = _str(config=config, key="snapshot_strategy")
    updated_at: str | None = _str(config=config, key="updated_at")
    observed_at: str | None = _str(config=config, key="observed_at")
    historical_input: str | None = _str(config=config, key="historical_input")
    initial_valid_from: str | None = _str(config=config, key="initial_valid_from")
    snapshot_full_refresh: str | None = _str(config=config, key="snapshot_full_refresh")
    snapshot_schema_change: str | None = _str(config=config, key="snapshot_schema_change")
    unique_key: object | None = config.values.get("unique_key")
    check_columns: object | None = config.values.get("check_columns")
    invalidate_hard_deletes: object | None = config.values.get("invalidate_hard_deletes")
    valid_from_column: str | None = _str(config=config, key="valid_from_column")
    valid_to_column: str | None = _str(config=config, key="valid_to_column")

    key: str
    for key in _SNAPSHOT_DISALLOWED_KEYS:
        if config.values.get(key) is not None:
            raise CompileInputError(
                f"model '{model_name}': {key} is not allowed on snapshot models"
            )

    if not _has_config_value(unique_key):
        raise CompileInputError(
            f"model '{model_name}': snapshot materialization requires unique_key"
        )
    if strategy is None:
        raise CompileInputError(
            f"model '{model_name}': snapshot materialization requires snapshot_strategy"
        )
    if strategy not in _VALID_SNAPSHOT_STRATEGIES:
        raise CompileInputError(
            f"model '{model_name}': unknown snapshot_strategy '{strategy}'; "
            f"valid values: {', '.join(sorted(_VALID_SNAPSHOT_STRATEGIES))}"
        )

    if strategy == SnapshotStrategy.TIMESTAMP and updated_at is None:
        raise CompileInputError(
            f"model '{model_name}': snapshot_strategy=timestamp requires updated_at"
        )
    if strategy == SnapshotStrategy.CHECK and not _has_config_value(check_columns):
        raise CompileInputError(
            f"model '{model_name}': snapshot_strategy=check requires check_columns"
        )
    if (
        strategy == SnapshotStrategy.CHECK
        and isinstance(check_columns, list)
        and SQL_WILDCARD_TOKEN in check_columns
        and len(check_columns) != 1
    ):
        raise CompileInputError(
            f"model '{model_name}': check_columns [*] cannot be combined with explicit columns"
        )

    if historical_input is not None and observed_at is None:
        raise CompileInputError(f"model '{model_name}': historical_input requires observed_at")
    if historical_input is not None and historical_input not in _VALID_HISTORICAL_INPUTS:
        raise CompileInputError(
            f"model '{model_name}': unknown historical_input '{historical_input}'; "
            f"valid values: {', '.join(sorted(_VALID_HISTORICAL_INPUTS))}"
        )
    if (
        observed_at is not None
        and strategy == SnapshotStrategy.TIMESTAMP
        and historical_input is None
    ):
        raise CompileInputError(
            f"model '{model_name}': timestamp snapshots with observed_at require "
            "historical_input snapshot or changes"
        )
    if strategy == SnapshotStrategy.CHECK and historical_input == HistoricalInput.CHANGES:
        raise CompileInputError(
            f"model '{model_name}': historical_input=changes is not valid with "
            "snapshot_strategy=check"
        )
    if invalidate_hard_deletes is not None and not isinstance(invalidate_hard_deletes, bool):
        raise CompileInputError(f"model '{model_name}': invalidate_hard_deletes must be a boolean")
    if invalidate_hard_deletes is True and historical_input == HistoricalInput.CHANGES:
        raise CompileInputError(
            f"model '{model_name}': invalidate_hard_deletes is not valid with "
            "historical_input=changes"
        )

    if initial_valid_from is not None and initial_valid_from not in _VALID_INITIAL_VALID_FROM:
        raise CompileInputError(
            f"model '{model_name}': unknown initial_valid_from '{initial_valid_from}'; "
            f"valid values: {', '.join(sorted(_VALID_INITIAL_VALID_FROM))}"
        )
    if initial_valid_from == InitialValidFrom.UPDATED_AT and updated_at is None:
        raise CompileInputError(
            f"model '{model_name}': initial_valid_from=updated_at requires updated_at"
        )
    if initial_valid_from == InitialValidFrom.OBSERVED_AT and observed_at is None:
        raise CompileInputError(
            f"model '{model_name}': initial_valid_from=observed_at requires observed_at"
        )

    if snapshot_full_refresh is not None:
        if snapshot_full_refresh not in _VALID_SNAPSHOT_FULL_REFRESH_POLICIES:
            raise CompileInputError(
                f"model '{model_name}': unknown snapshot_full_refresh "
                f"'{snapshot_full_refresh}'; valid values: "
                f"{', '.join(sorted(_VALID_SNAPSHOT_FULL_REFRESH_POLICIES))}"
            )

    if snapshot_schema_change is not None:
        if snapshot_schema_change not in _VALID_SNAPSHOT_SCHEMA_CHANGE_POLICIES:
            raise CompileInputError(
                f"model '{model_name}': unknown snapshot_schema_change "
                f"'{snapshot_schema_change}'; valid values: "
                f"{', '.join(sorted(_VALID_SNAPSHOT_SCHEMA_CHANGE_POLICIES))}"
            )
        if (
            config.values.get("contract") == ContractPolicy.ENFORCED.value
            and snapshot_schema_change == SnapshotSchemaChangePolicy.APPEND_NEW_COLUMNS
        ):
            raise CompileInputError(
                f"model '{model_name}': snapshot_schema_change=append_new_columns "
                "is not valid with contract enforced; add new columns to the contract "
                "or set contract none",
                code="K012",
            )

    if valid_from_column is not None and valid_to_column is not None:
        if valid_from_column.lower() == valid_to_column.lower():
            raise CompileInputError(
                f"model '{model_name}': valid_from_column and valid_to_column must differ"
            )

    declared_column_names: frozenset[str] | None = _contract_declared_column_names(
        config=config,
        declared_columns=declared_columns,
    )
    if declared_column_names is not None:
        _validate_declared_config_columns(
            column_names=_string_sequence(unique_key),
            config_key="unique_key",
            declared_column_names=declared_column_names,
            model_name=model_name,
        )
        if updated_at is not None:
            _validate_declared_config_column(
                column_name=updated_at,
                config_key="updated_at",
                declared_column_names=declared_column_names,
                model_name=model_name,
            )
        if observed_at is not None:
            _validate_declared_config_column(
                column_name=observed_at,
                config_key="observed_at",
                declared_column_names=declared_column_names,
                model_name=model_name,
            )
        if check_columns != [SQL_WILDCARD_TOKEN]:
            _validate_declared_config_columns(
                column_names=_string_sequence(check_columns),
                config_key="check_columns",
                declared_column_names=declared_column_names,
                model_name=model_name,
            )


def validate_custom_materialization_config(
    *,
    config: CompileModelConfig,
    model_name: str,
    custom_materialization_names: frozenset[str],
) -> None:
    """Validate config for custom materialization models."""

    materialized: str | None = _str(config=config, key="materialized")
    if materialized is None or materialized in _BUILTIN_MATERIALIZATION_TYPES:
        return

    if materialized not in custom_materialization_names:
        raise CompileInputError(
            f"model '{model_name}': unknown materialization '{materialized}'; "
            f"not a built-in type and no custom materialization with that name was discovered"
        )

    key: str
    for key in _CUSTOM_MATERIALIZATION_DISALLOWED_KEYS:
        if config.values.get(key) is not None:
            raise CompileInputError(
                f"model '{model_name}': {key} is not allowed on custom materializations"
            )


def validate_time_travel_retention(*, config: CompileModelConfig, model_name: str) -> None:
    """Reject managed retention on materializations without physical managed tables."""

    retention: ResolvedTimeTravelRetention = config.time_travel_retention
    if retention.unmanaged:
        return
    materialized: str | None = _str(config=config, key="materialized")
    if materialized == MaterializationType.VIEW:
        raise CompileInputError(
            f"model '{model_name}': managed time_travel_retention is not valid for views; "
            "set time_travel_retention disabled"
        )
    if not MaterializationType.is_table_backed(materialized=materialized):
        raise CompileInputError(
            f"model '{model_name}': managed time_travel_retention is not supported for "
            f"materialization '{materialized}'"
        )


def validate_table_type(*, config: CompileModelConfig, model_name: str) -> None:
    """Reject declared table type on materializations without managed tables."""

    if not config.table_type.declared:
        return
    materialized: str | None = _str(config=config, key="materialized")
    if materialized == MaterializationType.VIEW:
        raise CompileInputError(f"model '{model_name}': table_type is not valid for views")
    if not MaterializationType.is_table_backed(materialized=materialized):
        raise CompileInputError(
            f"model '{model_name}': table_type is not supported for materialization "
            f"'{materialized}'"
        )


def validate_storage_policies(*, config: CompileModelConfig, model_name: str) -> None:
    """Validate retention and table-type materialization applicability."""

    validate_time_travel_retention(config=config, model_name=model_name)
    validate_table_type(config=config, model_name=model_name)


def validate_placeholder_config(
    *,
    config: CompileModelConfig,
    model_name: str,
    query_sql: str,
    custom_materialization_names: frozenset[str],
) -> None:
    """Validate @@@placeholder usage and placeholders config consistency."""

    import re

    materialized: str | None = _str(config=config, key="materialized")
    is_custom: bool = materialized is not None and materialized in custom_materialization_names
    placeholders_config: object | None = config.values.get("placeholders")
    sql_placeholders: frozenset[str] = frozenset(re.findall(r"@@@(\w+)", query_sql))

    if not is_custom and sql_placeholders:
        raise CompileInputError(
            f"model '{model_name}': @@@placeholders are only allowed on custom materializations"
        )
    if not is_custom and placeholders_config is not None:
        raise CompileInputError(
            f"model '{model_name}': placeholders config is only allowed on custom materializations"
        )

    if is_custom and not sql_placeholders and placeholders_config is None:
        return

    declared_names: frozenset[str] = frozenset()
    if isinstance(placeholders_config, dict):
        declared_names = frozenset(str(k) for k in placeholders_config)

    missing_defaults: frozenset[str] = sql_placeholders - declared_names
    if missing_defaults:
        sorted_missing: str = ", ".join(sorted(missing_defaults))
        raise CompileInputError(
            f"model '{model_name}': @@@placeholders without default values "
            f"in placeholders config: {sorted_missing}"
        )

    unused_defaults: frozenset[str] = declared_names - sql_placeholders
    if unused_defaults:
        sorted_unused: str = ", ".join(sorted(unused_defaults))
        raise CompileInputError(
            f"model '{model_name}': placeholders config entries not used in SQL: {sorted_unused}"
        )


def _str(*, config: CompileModelConfig, key: str) -> str | None:
    """Extract a string value from config."""

    raw: object | None = config.values.get(key)
    return raw if isinstance(raw, str) else None


def _has_config_value(value: object | None) -> bool:
    return value is not None and value != () and value != []


def _contract_declared_column_names(
    *,
    config: CompileModelConfig,
    declared_columns: tuple[SchemaColumn, ...] | None = None,
) -> frozenset[str] | None:
    if config.values.get("contract") != ContractPolicy.ENFORCED:
        return None
    resolved_names: frozenset[str] = frozenset(column.name for column in declared_columns or ())
    raw_columns: object | None = config.values.get("columns")
    if not isinstance(raw_columns, dict):
        return resolved_names
    return resolved_names | frozenset(name for name in raw_columns if isinstance(name, str))


def _string_sequence(value: object | None) -> tuple[str, ...]:
    if isinstance(value, str):
        return (value,)
    if isinstance(value, list | tuple):
        return tuple(item for item in value if isinstance(item, str))
    return ()


def _validated_string_sequence(
    *, value: object, config_key: str, model_name: str
) -> tuple[str, ...]:
    if not isinstance(value, list | tuple) or not all(
        isinstance(item, str) and item for item in value
    ):
        raise CompileInputError(
            f"model '{model_name}': {config_key} must be a list of non-empty strings"
        )
    return tuple(item for item in value if isinstance(item, str))


def _validate_declared_config_columns(
    *,
    column_names: tuple[str, ...],
    config_key: str,
    declared_column_names: frozenset[str],
    model_name: str,
) -> None:
    column_name: str
    for column_name in column_names:
        _validate_declared_config_column(
            column_name=column_name,
            config_key=config_key,
            declared_column_names=declared_column_names,
            model_name=model_name,
        )


def _validate_declared_config_column(
    *,
    column_name: str,
    config_key: str,
    declared_column_names: frozenset[str],
    model_name: str,
) -> None:
    if column_name in declared_column_names:
        return
    raise CompileInputError(
        f"model '{model_name}': {config_key} references column '{column_name}' "
        "not declared in enforced contract"
    )


def _validate_timestamp_cursor_start(*, cursor_start: object, model_name: str) -> None:
    if isinstance(cursor_start, datetime | date):
        return
    if isinstance(cursor_start, str):
        try:
            datetime.fromisoformat(cursor_start)
        except ValueError as error:
            raise CompileInputError(
                f"model '{model_name}': cursor_start value '{cursor_start}' "
                f"is not a valid ISO timestamp: {error}"
            ) from None
        return
    raise CompileInputError(
        f"model '{model_name}': cursor_start for cursor_type=timestamp must be "
        "a string or date-like value"
    )


def _validate_integer_cursor_start(*, cursor_start: object, model_name: str) -> None:
    if isinstance(cursor_start, bool):
        raise CompileInputError(
            f"model '{model_name}': cursor_start for cursor_type=integer must be an integer"
        )
    if isinstance(cursor_start, int):
        return
    if isinstance(cursor_start, str):
        try:
            decimal_value: Decimal = Decimal(cursor_start)
        except InvalidOperation:
            raise CompileInputError(
                f"model '{model_name}': cursor_start value '{cursor_start}' is not a valid integer"
            ) from None
        if decimal_value != int(decimal_value):
            raise CompileInputError(
                f"model '{model_name}': cursor_start value '{cursor_start}' is not a whole number"
            )
        return
    raise CompileInputError(
        f"model '{model_name}': cursor_start for cursor_type=integer must be a string or integer"
    )
