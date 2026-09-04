"""Compile-time validation of model config combinations."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from typing import cast

from sqlbuild.compiler.compile.constants import (
    MICROBATCH_LIMIT_ACTION_KEY,
    MICROBATCH_LIMIT_MAX_BATCHES_KEY,
    SQL_WILDCARD_TOKEN,
    WATERMARK_CURSOR_INPUT_BLOCK_KEYS,
)
from sqlbuild.compiler.compile.exceptions import CompileInputError
from sqlbuild.compiler.compile.models import CompileModelConfig
from sqlbuild.compiler.planner.types import (
    ContractPolicy,
    CursorGrain,
    CursorInputRole,
    CursorType,
    CursorWatermarkMode,
    HistoricalInput,
    IncrementalMode,
    IncrementalStrategy,
    InitialValidFrom,
    MaterializationType,
    MicrobatchStrategy,
    SnapshotFullRefreshPolicy,
    SnapshotSchemaChangePolicy,
    SnapshotStrategy,
)
from sqlbuild.cursor_algebra.constants import GRAIN_BATCH_SIZE
from sqlbuild.cursor_algebra.models import Duration
from sqlbuild.spec.contracts.constants import (
    CURSOR_POLICY_DISABLED,
    EFFECTIVE_BATCH_SIZE_TOKEN,
    ZERO_DAY_CURSOR_DURATION,
)
from sqlbuild.spec.contracts.main.get_config_str import get_config_str
from sqlbuild.spec.contracts.models import (
    ResolvedTimeTravelRetention,
    SchemaColumn,
    SettingsConfig,
)
from sqlbuild.spec.contracts.types import FutureCursorAction, MicrobatchLimitAction

_VALID_STRATEGIES: frozenset[str] = frozenset(s.value for s in IncrementalStrategy)
_VALID_CURSOR_TYPES: frozenset[str] = frozenset(ct.value for ct in CursorType)
_VALID_CURSOR_GRAINS: frozenset[str] = frozenset(cg.value for cg in CursorGrain)
_VALID_INCREMENTAL_MODES: frozenset[str] = frozenset(m.value for m in IncrementalMode)
_VALID_MICROBATCH_STRATEGIES: frozenset[str] = frozenset(m.value for m in MicrobatchStrategy)
_VALID_WATERMARK_MODES: frozenset[str] = frozenset(m.value for m in CursorWatermarkMode)
_VALID_CURSOR_INPUT_ROLES: frozenset[str] = frozenset(role.value for role in CursorInputRole)
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
    "cursor_end",
    "microbatch_strategy",
    "cursor_watermark_mode",
    "max_microbatches",
    "microbatch_limit",
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
    "cursor_end",
    "microbatch_strategy",
    "cursor_watermark_mode",
    "max_microbatches",
    "microbatch_limit",
    "lookback",
)


@dataclass(frozen=True)
class _IncrementalConfigValues:
    strategy: str | None
    cursor: str | None
    cursor_type: str | None
    cursor_start: object | None
    cursor_end: object | None
    cursor_start_max_ahead: object | None
    cursor_start_max_action: object | None
    cursor_future_max_distance: object | None
    cursor_future_action: object | None
    append_cursor_inclusive: object | None
    unique_key: object | None
    lookback: str | None
    incremental_mode: str | None
    batch_size: object | None
    batch_concurrency: object | None
    unaccounted_partition_policy: object | None
    cursor_inputs: object | None
    cursor_filter_inputs: object | None
    cursor_watermark_inputs: object | None
    microbatch_strategy: str | None
    cursor_watermark_mode: str | None
    max_microbatches: object | None
    microbatch_limit: object | None
    cursor_grain: str | None
    replay_on_change: object | None
    merge_exclude_columns: object | None
    full_refresh: object | None


@dataclass(frozen=True)
class _CursorInputValidation:
    values: _IncrementalConfigValues
    ref_count: int


def validate_incremental_config(
    *,
    config: CompileModelConfig,
    model_name: str,
    ref_count: int,
    known_input_names: frozenset[str],
    declared_columns: tuple[SchemaColumn, ...] | None = None,
) -> None:
    """Validate incremental model config rules after layering."""

    materialized: str | None = get_config_str(values=config.values, key="materialized")
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

    values: _IncrementalConfigValues = _resolve_incremental_config_values(config=config)
    _validate_incremental_core(model_name=model_name, values=values)
    _validate_incremental_batching(
        model_name=model_name,
        ref_count=ref_count,
        known_input_names=known_input_names,
        values=values,
    )
    _validate_incremental_write_strategy(model_name=model_name, values=values)
    _validate_incremental_contract(
        config=config,
        model_name=model_name,
        declared_columns=declared_columns,
        values=values,
    )
    if values.lookback is not None and values.cursor is None:
        raise CompileInputError(
            f"model '{model_name}': lookback is only valid with cursor-based incremental"
        )


def _validate_incremental_core(*, model_name: str, values: _IncrementalConfigValues) -> None:
    if values.replay_on_change is not None and not isinstance(values.replay_on_change, str):
        raise CompileInputError(f"model '{model_name}': replay_on_change must be a string")
    if values.strategy is None:
        raise CompileInputError(
            f"model '{model_name}': incremental materialization requires incremental_strategy"
        )
    if values.strategy not in _VALID_STRATEGIES:
        raise CompileInputError(
            f"model '{model_name}': unknown incremental_strategy '{values.strategy}'; "
            f"valid values: {', '.join(sorted(_VALID_STRATEGIES))}"
        )
    _validate_incremental_cursor_rules(
        model_name=model_name,
        cursor=values.cursor,
        cursor_type=values.cursor_type,
        cursor_grain=values.cursor_grain,
        cursor_start=values.cursor_start,
        cursor_end=values.cursor_end,
        append_cursor_inclusive=values.append_cursor_inclusive,
        strategy=values.strategy,
    )
    _validate_cursor_safety_overrides(
        model_name=model_name,
        cursor=values.cursor,
        cursor_start_max_ahead=values.cursor_start_max_ahead,
        cursor_start_max_action=values.cursor_start_max_action,
        cursor_future_max_distance=values.cursor_future_max_distance,
        cursor_future_action=values.cursor_future_action,
    )


def _validate_incremental_batching(
    *,
    model_name: str,
    ref_count: int,
    known_input_names: frozenset[str],
    values: _IncrementalConfigValues,
) -> None:
    if (
        values.incremental_mode is not None
        and values.incremental_mode not in _VALID_INCREMENTAL_MODES
    ):
        raise CompileInputError(
            f"model '{model_name}': unknown incremental_mode '{values.incremental_mode}'; "
            f"valid values: {', '.join(sorted(_VALID_INCREMENTAL_MODES))}"
        )
    _validate_microbatch_batch_size(
        model_name=model_name,
        batch_size=values.batch_size,
        incremental_mode=values.incremental_mode,
        cursor=values.cursor,
        cursor_type=values.cursor_type,
        cursor_grain=values.cursor_grain,
    )
    _validate_microbatch_state_config(
        model_name=model_name,
        strategy=values.strategy,
        incremental_mode=values.incremental_mode,
        batch_concurrency=values.batch_concurrency,
        unaccounted_partition_policy=values.unaccounted_partition_policy,
    )
    _validate_cursor_input_config(
        model_name=model_name,
        known_input_names=known_input_names,
        inputs=_CursorInputValidation(values=values, ref_count=ref_count),
    )
    resolved_limit, resolved_limit_action = _validate_model_microbatch_limit(
        model_name=model_name,
        max_microbatches=values.max_microbatches,
        microbatch_limit=values.microbatch_limit,
        microbatch_strategy=values.microbatch_strategy,
    )
    if resolved_limit is not None:
        _validate_static_watermark_limit(
            model_name=model_name,
            max_microbatches=resolved_limit,
            lookback=values.lookback,
            batch_size=values.batch_size,
            incremental_strategy=values.strategy,
            action=resolved_limit_action,
            cursor_grain=values.cursor_grain,
        )


def _validate_incremental_write_strategy(
    *, model_name: str, values: _IncrementalConfigValues
) -> None:
    has_unique_key: bool = values.unique_key not in (None, (), [])
    if (
        values.strategy == IncrementalStrategy.DELETE_INSERT
        and values.cursor is None
        and not has_unique_key
    ):
        raise CompileInputError(
            f"model '{model_name}': delete_insert without cursor requires unique_key"
        )
    if values.strategy == IncrementalStrategy.MERGE and not has_unique_key:
        raise CompileInputError(f"model '{model_name}': merge strategy requires unique_key")
    if values.merge_exclude_columns is not None:
        excluded_columns: tuple[str, ...] = _validated_string_sequence(
            value=values.merge_exclude_columns,
            config_key="merge_exclude_columns",
            model_name=model_name,
        )
        if values.strategy != IncrementalStrategy.MERGE:
            raise CompileInputError(
                f"model '{model_name}': merge_exclude_columns requires incremental_strategy=merge"
            )
        if len({column.lower() for column in excluded_columns}) != len(excluded_columns):
            raise CompileInputError(
                f"model '{model_name}': merge_exclude_columns contains duplicate columns"
            )
        unique_key_columns: frozenset[str] = frozenset(
            column.lower() for column in _string_sequence(values.unique_key)
        )
        overlap: tuple[str, ...] = tuple(
            column for column in excluded_columns if column.lower() in unique_key_columns
        )
        if overlap:
            raise CompileInputError(
                f"model '{model_name}': merge_exclude_columns cannot include unique_key "
                f"column(s): {', '.join(overlap)}"
            )
    if values.full_refresh is not None and not isinstance(values.full_refresh, bool):
        raise CompileInputError(f"model '{model_name}': full_refresh must be a boolean")


def _validate_incremental_contract(
    *,
    config: CompileModelConfig,
    model_name: str,
    declared_columns: tuple[SchemaColumn, ...] | None,
    values: _IncrementalConfigValues,
) -> None:
    declared_column_names: frozenset[str] | None = _contract_declared_column_names(
        config=config,
        declared_columns=declared_columns,
    )
    if declared_column_names is not None:
        if values.cursor is not None:
            _validate_declared_config_column(
                column_name=values.cursor,
                config_key="cursor",
                declared_column_names=declared_column_names,
                model_name=model_name,
            )
        _validate_declared_config_columns(
            column_names=_string_sequence(values.unique_key),
            config_key="unique_key",
            declared_column_names=declared_column_names,
            model_name=model_name,
        )
        _validate_declared_config_columns(
            column_names=_string_sequence(values.merge_exclude_columns),
            config_key="merge_exclude_columns",
            declared_column_names=declared_column_names,
            model_name=model_name,
        )


def _resolve_incremental_config_values(*, config: CompileModelConfig) -> _IncrementalConfigValues:
    return _IncrementalConfigValues(
        strategy=get_config_str(values=config.values, key="incremental_strategy"),
        cursor=get_config_str(values=config.values, key="cursor"),
        cursor_type=get_config_str(values=config.values, key="cursor_type"),
        cursor_start=config.values.get("cursor_start"),
        cursor_end=config.values.get("cursor_end"),
        cursor_start_max_ahead=config.values.get("cursor_start_max_ahead"),
        cursor_start_max_action=config.values.get("cursor_start_max_action"),
        cursor_future_max_distance=config.values.get("cursor_future_max_distance"),
        cursor_future_action=config.values.get("cursor_future_action"),
        append_cursor_inclusive=config.values.get("append_cursor_inclusive"),
        unique_key=config.values.get("unique_key"),
        lookback=get_config_str(values=config.values, key="lookback"),
        incremental_mode=get_config_str(values=config.values, key="incremental_mode"),
        batch_size=get_config_str(values=config.values, key="batch_size"),
        batch_concurrency=config.values.get("batch_concurrency"),
        unaccounted_partition_policy=config.values.get("unaccounted_partition_policy"),
        cursor_inputs=config.values.get("cursor_inputs"),
        cursor_filter_inputs=config.values.get("cursor_filter_inputs"),
        cursor_watermark_inputs=config.values.get("cursor_watermark_inputs"),
        microbatch_strategy=get_config_str(values=config.values, key="microbatch_strategy"),
        cursor_watermark_mode=get_config_str(values=config.values, key="cursor_watermark_mode"),
        max_microbatches=config.values.get("max_microbatches"),
        microbatch_limit=config.values.get("microbatch_limit"),
        cursor_grain=get_config_str(values=config.values, key="cursor_grain"),
        replay_on_change=config.values.get("replay_on_change"),
        merge_exclude_columns=config.values.get("merge_exclude_columns"),
        full_refresh=config.values.get("full_refresh"),
    )


def _validate_microbatch_batch_size(
    *,
    model_name: str,
    batch_size: object | None,
    incremental_mode: str | None,
    cursor: str | None,
    cursor_type: str | None,
    cursor_grain: str | None,
) -> None:
    if batch_size is not None and incremental_mode != IncrementalMode.MICROBATCH:
        raise CompileInputError(
            f"model '{model_name}': batch_size is only valid with incremental_mode=microbatch"
        )
    if batch_size == EFFECTIVE_BATCH_SIZE_TOKEN and (
        cursor is None or cursor_type != CursorType.TIMESTAMP or cursor_grain is None
    ):
        raise CompileInputError(
            f"model '{model_name}': batch_size=effective requires a timestamp cursor "
            "with cursor_grain"
        )


def _validate_cursor_input_config(
    *,
    model_name: str,
    known_input_names: frozenset[str],
    inputs: _CursorInputValidation,
) -> None:
    """Validate the strategy-specific canonical cursor input contract."""

    for removed_field, value in (
        ("cursor_filter_inputs", inputs.values.cursor_filter_inputs),
        ("cursor_watermark_inputs", inputs.values.cursor_watermark_inputs),
    ):
        if value is not None:
            raise CompileInputError(
                f"model '{model_name}': {removed_field} has been removed; declare "
                "microbatch_strategy and use strategy-specific cursor_inputs"
            )
    if (
        inputs.values.microbatch_strategy is not None
        and inputs.values.incremental_mode != IncrementalMode.MICROBATCH
    ):
        raise CompileInputError(
            f"model '{model_name}': microbatch_strategy is only valid with "
            "incremental_mode=microbatch"
        )
    if (
        inputs.values.incremental_mode == IncrementalMode.MICROBATCH
        and inputs.values.microbatch_strategy is None
    ):
        raise CompileInputError(
            f"model '{model_name}': incremental_mode=microbatch requires explicit "
            "microbatch_strategy (rolling_window or watermark)"
        )
    if (
        inputs.values.microbatch_strategy is not None
        and inputs.values.microbatch_strategy not in _VALID_MICROBATCH_STRATEGIES
    ):
        raise CompileInputError(
            f"model '{model_name}': unknown microbatch_strategy "
            f"'{inputs.values.microbatch_strategy}'; "
            f"valid values: {', '.join(sorted(_VALID_MICROBATCH_STRATEGIES))}"
        )
    if (
        inputs.values.microbatch_strategy == MicrobatchStrategy.ROLLING_WINDOW
        and inputs.values.cursor_type != CursorType.TIMESTAMP
    ):
        raise CompileInputError(
            f"model '{model_name}': rolling_window requires cursor_type=timestamp"
        )
    if inputs.values.cursor_inputs is not None and inputs.values.cursor is None:
        raise CompileInputError(f"model '{model_name}': cursor_inputs requires cursor")
    if (
        inputs.values.microbatch_strategy == MicrobatchStrategy.WATERMARK
        and inputs.values.cursor_inputs is None
    ) or (
        inputs.values.microbatch_strategy == MicrobatchStrategy.ROLLING_WINDOW
        and inputs.ref_count > 0
        and inputs.values.cursor_inputs is None
    ):
        raise CompileInputError(f"model '{model_name}': microbatch strategy requires cursor_inputs")
    if inputs.values.cursor_inputs is not None:
        if inputs.values.microbatch_strategy == MicrobatchStrategy.WATERMARK:
            _validate_watermark_cursor_inputs(
                model_name=model_name,
                value=inputs.values.cursor_inputs,
                known_input_names=known_input_names,
            )
        else:
            _validate_cursor_input_map(
                model_name=model_name,
                config_field="cursor_inputs",
                value=inputs.values.cursor_inputs,
            )
            _validate_known_cursor_inputs(
                model_name=model_name,
                value=inputs.values.cursor_inputs,
                known_input_names=known_input_names,
            )
    if inputs.values.microbatch_strategy == MicrobatchStrategy.WATERMARK:
        if inputs.values.cursor_watermark_mode not in _VALID_WATERMARK_MODES:
            raise CompileInputError(
                f"model '{model_name}': watermark strategy requires "
                "cursor_watermark_mode all or any"
            )
    elif inputs.values.cursor_watermark_mode is not None:
        raise CompileInputError(
            f"model '{model_name}': cursor_watermark_mode is only valid with "
            "microbatch_strategy=watermark"
        )
    if inputs.values.max_microbatches is not None:
        if (
            isinstance(inputs.values.max_microbatches, bool)
            or not isinstance(inputs.values.max_microbatches, int)
            or inputs.values.max_microbatches < 1
        ):
            raise CompileInputError(
                f"model '{model_name}': max_microbatches must be a positive integer"
            )
        if inputs.values.microbatch_strategy != MicrobatchStrategy.WATERMARK:
            raise CompileInputError(
                f"model '{model_name}': max_microbatches is only valid with "
                "microbatch_strategy=watermark"
            )
    if (
        inputs.values.cursor is not None
        and inputs.ref_count > 1
        and inputs.values.cursor_inputs is None
    ):
        raise CompileInputError(
            f"model '{model_name}': models with cursor and multiple inputs require explicit "
            "cursor_inputs"
        )


def _validate_model_microbatch_limit(
    *,
    model_name: str,
    max_microbatches: object | None,
    microbatch_limit: object | None,
    microbatch_strategy: str | None,
) -> tuple[int | None, MicrobatchLimitAction | None]:
    if max_microbatches is not None and microbatch_limit is not None:
        raise CompileInputError(
            f"model '{model_name}': use either max_microbatches or microbatch_limit, not both"
        )
    if microbatch_limit is None:
        return (
            (
                max_microbatches
                if isinstance(max_microbatches, int) and not isinstance(max_microbatches, bool)
                else None
            ),
            None,
        )
    if not isinstance(microbatch_limit, dict) or set(microbatch_limit) != {
        MICROBATCH_LIMIT_MAX_BATCHES_KEY,
        MICROBATCH_LIMIT_ACTION_KEY,
    }:
        raise CompileInputError(
            f"model '{model_name}': microbatch_limit requires exactly max_batches and action"
        )
    limit_mapping: dict[str, object] = cast(dict[str, object], microbatch_limit)
    max_batches: object | None = limit_mapping.get(MICROBATCH_LIMIT_MAX_BATCHES_KEY)
    action: object | None = limit_mapping.get(MICROBATCH_LIMIT_ACTION_KEY)
    if isinstance(max_batches, bool) or not isinstance(max_batches, int) or max_batches < 1:
        raise CompileInputError(
            f"model '{model_name}': microbatch_limit max_batches must be a positive integer"
        )
    valid_actions: frozenset[str] = frozenset(item.value for item in MicrobatchLimitAction)
    if not isinstance(action, str) or action not in valid_actions:
        raise CompileInputError(
            f"model '{model_name}': microbatch_limit action must be one of: "
            + ", ".join(sorted(valid_actions))
        )
    if microbatch_strategy != MicrobatchStrategy.WATERMARK:
        raise CompileInputError(
            f"model '{model_name}': microbatch_limit is only valid with "
            "microbatch_strategy=watermark"
        )
    return max_batches, MicrobatchLimitAction(action)


def _validate_known_cursor_inputs(
    *, model_name: str, value: object, known_input_names: frozenset[str]
) -> None:
    if not isinstance(value, dict):
        return
    for input_name in value:
        if str(input_name) not in known_input_names:
            expected_names: str = ", ".join(sorted(known_input_names))
            raise CompileInputError(
                f"model '{model_name}': cursor_inputs references unknown input "
                f"'{input_name}'; expected one of: {expected_names}"
            )


def _validate_watermark_cursor_inputs(
    *, model_name: str, value: object, known_input_names: frozenset[str]
) -> None:
    if not isinstance(value, dict) or not value:
        raise CompileInputError(
            f"model '{model_name}': watermark cursor_inputs must be a non-empty relation map"
        )
    has_watermark: bool = False
    for relation, block in value.items():
        if not isinstance(relation, str) or not relation.strip() or not isinstance(block, dict):
            raise CompileInputError(
                f"model '{model_name}': watermark cursor_inputs relation '{relation}' must use "
                "(column ..., roles [...])"
            )
        if set(block) != WATERMARK_CURSOR_INPUT_BLOCK_KEYS:
            raise CompileInputError(
                f"model '{model_name}': cursor_inputs relation '{relation}' requires exactly "
                "column and roles"
            )
        typed_block: dict[object, object] = cast(dict[object, object], block)
        column: object | None = typed_block.get("column")
        roles: object | None = typed_block.get("roles")
        if not isinstance(column, str) or not column.strip():
            raise CompileInputError(
                f"model '{model_name}': cursor_inputs column for relation '{relation}' must be "
                "a non-empty string"
            )
        if (
            not isinstance(roles, list)
            or not roles
            or any(role not in _VALID_CURSOR_INPUT_ROLES for role in roles)
        ):
            raise CompileInputError(
                f"model '{model_name}': cursor_inputs roles for relation '{relation}' must be a "
                "non-empty list containing only filter and/or watermark"
            )
        if len(set(roles)) != len(roles):
            raise CompileInputError(
                f"model '{model_name}': cursor_inputs relation '{relation}' contains "
                "duplicate roles"
            )
        has_watermark = has_watermark or CursorInputRole.WATERMARK in roles
        if CursorInputRole.FILTER in roles and relation not in known_input_names:
            expected_names: str = ", ".join(sorted(known_input_names))
            raise CompileInputError(
                f"model '{model_name}': filter role references input '{relation}' that is not "
                f"directly filterable; expected one of: {expected_names}"
            )
    if not has_watermark:
        raise CompileInputError(
            f"model '{model_name}': watermark strategy requires at least one watermark role"
        )


def _validate_static_watermark_limit(
    *,
    model_name: str,
    max_microbatches: int,
    lookback: str | None,
    batch_size: object | None,
    incremental_strategy: str | None,
    action: MicrobatchLimitAction | None,
    cursor_grain: str | None,
) -> None:
    effective_batch_size: object = batch_size
    if batch_size == EFFECTIVE_BATCH_SIZE_TOKEN and cursor_grain is not None:
        effective_batch_size = GRAIN_BATCH_SIZE.get(CursorGrain(cursor_grain), batch_size)
    effective_lookback: str | None = lookback
    if (
        effective_lookback is None
        and action == MicrobatchLimitAction.CAP_FROM_START
        and incremental_strategy in {IncrementalStrategy.DELETE_INSERT, IncrementalStrategy.MERGE}
        and isinstance(effective_batch_size, str)
    ):
        effective_lookback = effective_batch_size
    if effective_lookback is None or not isinstance(effective_batch_size, str):
        return
    lookback_duration: Duration | None = Duration.parse(effective_lookback)
    batch_duration: Duration | None = Duration.parse(effective_batch_size)
    if lookback_duration is None or batch_duration is None:
        return
    if not lookback_duration.has_calendar_component and not batch_duration.has_calendar_component:
        if batch_duration.fixed_seconds == 0:
            return
        lookback_batches: int = (
            lookback_duration.fixed_seconds + batch_duration.fixed_seconds - 1
        ) // batch_duration.fixed_seconds
    elif lookback_duration.fixed_seconds == 0 and batch_duration.fixed_seconds == 0:
        if batch_duration.total_months == 0:
            return
        lookback_batches = (
            lookback_duration.total_months + batch_duration.total_months - 1
        ) // batch_duration.total_months
    else:
        if action == MicrobatchLimitAction.CAP_FROM_START:
            raise CompileInputError(
                f"model '{model_name}': cap_from_start cannot prove forward progress when "
                "lookback and batch_size mix calendar and fixed duration components; use "
                "compatible fixed or calendar durations"
            )
        return
    required: int = (
        lookback_batches + 1 + (1 if action == MicrobatchLimitAction.CAP_FROM_START else 0)
    )
    if max_microbatches < required:
        raise CompileInputError(
            f"model '{model_name}': max_microbatches {max_microbatches} is below the "
            f"ordinary lookback requirement of {required} batches"
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
    strategy: str | None,
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
    cursor_end: object | None,
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
    if cursor_end is not None and cursor is None:
        raise CompileInputError(f"model '{model_name}': cursor_end requires cursor")
    if cursor_end is not None and cursor_type == CursorType.TIMESTAMP:
        _validate_timestamp_cursor_start(cursor_start=cursor_end, model_name=model_name)
    if cursor_end is not None and cursor_type == CursorType.INTEGER:
        _validate_integer_cursor_start(cursor_start=cursor_end, model_name=model_name)
    if (
        cursor_start is not None
        and cursor_end is not None
        and _cursor_contract_key(value=cursor_start, cursor_type=cursor_type)
        >= _cursor_contract_key(value=cursor_end, cursor_type=cursor_type)
    ):
        raise CompileInputError(
            f"model '{model_name}': cursor_start must be before exclusive cursor_end"
        )
    if append_cursor_inclusive is not None and not isinstance(append_cursor_inclusive, bool):
        raise CompileInputError(f"model '{model_name}': append_cursor_inclusive must be a boolean")
    if append_cursor_inclusive is not None and strategy != IncrementalStrategy.APPEND:
        raise CompileInputError(
            f"model '{model_name}': append_cursor_inclusive is only valid with append strategy"
        )
    if append_cursor_inclusive is not None and cursor is None:
        raise CompileInputError(f"model '{model_name}': append_cursor_inclusive requires cursor")


def _cursor_contract_key(*, value: object, cursor_type: str | None) -> Decimal:
    if cursor_type == CursorType.INTEGER:
        return Decimal(str(value))
    parsed: datetime = datetime.fromisoformat(str(value))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    else:
        parsed = parsed.astimezone(UTC)
    return Decimal(str(parsed.timestamp()))


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
    if cursor_start_max_ahead is not None and (
        not isinstance(cursor_start_max_ahead, str)
        or (
            cursor_start_max_ahead not in {CURSOR_POLICY_DISABLED, ZERO_DAY_CURSOR_DURATION}
            and Duration.parse(cursor_start_max_ahead) is None
        )
    ):
        raise CompileInputError(
            f"model '{model_name}': cursor_start_max_ahead must be a duration or 'disabled'"
        )
    if cursor_future_max_distance is not None and (
        not isinstance(cursor_future_max_distance, str)
        or (
            cursor_future_max_distance not in {CURSOR_POLICY_DISABLED, ZERO_DAY_CURSOR_DURATION}
            and Duration.parse(cursor_future_max_distance) is None
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

    materialized: str | None = get_config_str(values=config.values, key="materialized")
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

    materialized: str | None = get_config_str(values=config.values, key="materialized")
    if materialized != MaterializationType.SNAPSHOT:
        return

    strategy: str | None = get_config_str(values=config.values, key="snapshot_strategy")
    updated_at: str | None = get_config_str(values=config.values, key="updated_at")
    observed_at: str | None = get_config_str(values=config.values, key="observed_at")
    historical_input: str | None = get_config_str(values=config.values, key="historical_input")
    initial_valid_from: str | None = get_config_str(values=config.values, key="initial_valid_from")
    snapshot_full_refresh: str | None = get_config_str(
        values=config.values, key="snapshot_full_refresh"
    )
    snapshot_schema_change: str | None = get_config_str(
        values=config.values, key="snapshot_schema_change"
    )
    unique_key: object | None = config.values.get("unique_key")
    check_columns: object | None = config.values.get("check_columns")
    invalidate_hard_deletes: object | None = config.values.get("invalidate_hard_deletes")
    valid_from_column: str | None = get_config_str(values=config.values, key="valid_from_column")
    valid_to_column: str | None = get_config_str(values=config.values, key="valid_to_column")

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

    materialized: str | None = get_config_str(values=config.values, key="materialized")
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
    materialized: str | None = get_config_str(values=config.values, key="materialized")
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
    materialized: str | None = get_config_str(values=config.values, key="materialized")
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

    materialized: str | None = get_config_str(values=config.values, key="materialized")
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
