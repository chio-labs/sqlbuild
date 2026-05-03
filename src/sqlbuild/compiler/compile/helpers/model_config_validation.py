"""Compile-time validation of model config combinations."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from sqlbuild.compiler.compile.exceptions import CompileInputError
from sqlbuild.compiler.compile.models import CompileModelConfig
from sqlbuild.compiler.planner.types import (
    CursorGrain,
    CursorType,
    IncrementalMode,
    IncrementalStrategy,
    MaterializationType,
)

_VALID_STRATEGIES: frozenset[str] = frozenset(s.value for s in IncrementalStrategy)
_VALID_CURSOR_TYPES: frozenset[str] = frozenset(ct.value for ct in CursorType)
_VALID_CURSOR_GRAINS: frozenset[str] = frozenset(cg.value for cg in CursorGrain)
_VALID_INCREMENTAL_MODES: frozenset[str] = frozenset(m.value for m in IncrementalMode)
_BUILTIN_MATERIALIZATION_TYPES: frozenset[str] = frozenset(
    (MaterializationType.VIEW, MaterializationType.TABLE, MaterializationType.INCREMENTAL)
)
_INCREMENTAL_ONLY_KEYS: tuple[str, ...] = (
    "on_schema_change",
    "schema_change_backfill",
    "append_cursor_inclusive",
)
_CUSTOM_MATERIALIZATION_DISALLOWED_KEYS: tuple[str, ...] = (
    "on_schema_change",
    "schema_change_backfill",
    "incremental_strategy",
    "incremental_mode",
    "append_cursor_inclusive",
    "batch_size",
    "cursor",
    "cursor_type",
    "cursor_grain",
    "cursor_inputs",
    "lookback",
    "query_change_backfill",
)


def validate_incremental_config(
    *,
    config: CompileModelConfig,
    model_name: str,
    ref_count: int,
    known_input_names: frozenset[str],
) -> None:
    """Validate incremental model config rules after layering.

    Only runs for models with materialized=incremental. Raises CompileInputError
    on invalid config combinations.
    """

    materialized: str | None = _str(config, "materialized")
    if materialized != MaterializationType.INCREMENTAL:
        return

    strategy: str | None = _str(config, "incremental_strategy")
    cursor: str | None = _str(config, "cursor")
    cursor_type: str | None = _str(config, "cursor_type")
    cursor_start: object | None = config.values.get("cursor_start")
    append_cursor_inclusive: object | None = config.values.get("append_cursor_inclusive")
    unique_key: object | None = config.values.get("unique_key")
    has_unique_key: bool = unique_key is not None and unique_key != () and unique_key != []
    lookback: str | None = _str(config, "lookback")
    incremental_mode: str | None = _str(config, "incremental_mode")
    batch_size: object | None = config.values.get("batch_size")
    batch_concurrency: object | None = config.values.get("batch_concurrency")
    cursor_inputs: object | None = config.values.get("cursor_inputs")
    cursor_grain: str | None = _str(config, "cursor_grain")
    if strategy is None:
        raise CompileInputError(
            f"model '{model_name}': incremental materialization requires incremental_strategy"
        )
    if strategy not in _VALID_STRATEGIES:
        raise CompileInputError(
            f"model '{model_name}': unknown incremental_strategy '{strategy}'; "
            f"valid values: {', '.join(sorted(_VALID_STRATEGIES))}"
        )

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

    if cursor_inputs is not None and cursor is None:
        raise CompileInputError(f"model '{model_name}': cursor_inputs requires cursor")
    if isinstance(cursor_inputs, dict):
        input_name: object
        for input_name in cursor_inputs:
            if str(input_name) not in known_input_names:
                expected_names: str = ", ".join(sorted(known_input_names))
                raise CompileInputError(
                    f"model '{model_name}': cursor_inputs references unknown input "
                    f"'{input_name}'; expected one of: {expected_names}"
                )
    if cursor is not None and ref_count > 1 and cursor_inputs is None:
        raise CompileInputError(
            f"model '{model_name}': models with cursor and multiple inputs "
            f"require explicit cursor_inputs"
        )

    if strategy == IncrementalStrategy.DELETE_INSERT and cursor is None and not has_unique_key:
        raise CompileInputError(
            f"model '{model_name}': delete_insert without cursor requires unique_key"
        )
    if strategy == IncrementalStrategy.MERGE and not has_unique_key:
        raise CompileInputError(f"model '{model_name}': merge strategy requires unique_key")

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
    if batch_concurrency is not None:
        raise CompileInputError(
            f"model '{model_name}': batch_concurrency is not supported; "
            f"microbatch processes batches serially"
        )


def validate_non_incremental_config(
    *,
    config: CompileModelConfig,
    model_name: str,
) -> None:
    """Reject incremental-only config keys on non-incremental models."""

    materialized: str | None = _str(config, "materialized")
    if materialized == MaterializationType.INCREMENTAL:
        return

    key: str
    for key in _INCREMENTAL_ONLY_KEYS:
        if config.values.get(key) is not None:
            raise CompileInputError(
                f"model '{model_name}': {key} is only valid for incremental models"
            )


def validate_custom_materialization_config(
    *,
    config: CompileModelConfig,
    model_name: str,
    custom_materialization_names: frozenset[str],
) -> None:
    """Validate config for custom materialization models."""

    materialized: str | None = _str(config, "materialized")
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


def validate_placeholder_config(
    *,
    config: CompileModelConfig,
    model_name: str,
    query_sql: str,
    custom_materialization_names: frozenset[str],
) -> None:
    """Validate @@placeholder usage and placeholders config consistency."""

    import re

    materialized: str | None = _str(config, "materialized")
    is_custom: bool = materialized is not None and materialized in custom_materialization_names
    placeholders_config: object | None = config.values.get("placeholders")
    sql_placeholders: frozenset[str] = frozenset(re.findall(r"@@(\w+)", query_sql))

    if not is_custom and sql_placeholders:
        raise CompileInputError(
            f"model '{model_name}': @@placeholders are only allowed on custom materializations"
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
            f"model '{model_name}': @@placeholders without default values "
            f"in placeholders config: {sorted_missing}"
        )

    unused_defaults: frozenset[str] = declared_names - sql_placeholders
    if unused_defaults:
        sorted_unused: str = ", ".join(sorted(unused_defaults))
        raise CompileInputError(
            f"model '{model_name}': placeholders config entries not used in SQL: {sorted_unused}"
        )


def _str(config: CompileModelConfig, key: str) -> str | None:
    """Extract a string value from config."""

    raw: object | None = config.values.get(key)
    return raw if isinstance(raw, str) else None


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
