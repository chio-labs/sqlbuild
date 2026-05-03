"""Compile-time validation of incremental model config combinations."""

from __future__ import annotations

from sqlbuild.compiler.compile.exceptions import CompileInputError
from sqlbuild.compiler.compile.models import CompileModelConfig
from sqlbuild.compiler.planner.types import (
    CursorType,
    IncrementalMode,
    IncrementalStrategy,
    MaterializationType,
)

_VALID_STRATEGIES: frozenset[str] = frozenset(s.value for s in IncrementalStrategy)
_VALID_CURSOR_TYPES: frozenset[str] = frozenset(ct.value for ct in CursorType)
_VALID_INCREMENTAL_MODES: frozenset[str] = frozenset(m.value for m in IncrementalMode)


def validate_incremental_config(
    *,
    config: CompileModelConfig,
    model_name: str,
    ref_count: int,
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
    unique_key: object | None = config.values.get("unique_key")
    has_unique_key: bool = unique_key is not None and unique_key != () and unique_key != []
    lookback: str | None = _str(config, "lookback")
    incremental_mode: str | None = _str(config, "incremental_mode")
    batch_size: object | None = config.values.get("batch_size")
    batch_concurrency: object | None = config.values.get("batch_concurrency")
    cursor_inputs: object | None = config.values.get("cursor_inputs")

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

    if strategy == IncrementalStrategy.APPEND and cursor is not None:
        raise CompileInputError(f"model '{model_name}': cursor is not allowed with append strategy")

    if cursor_inputs is not None and cursor is None:
        raise CompileInputError(f"model '{model_name}': cursor_inputs requires cursor")
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
    if batch_concurrency is not None and incremental_mode != IncrementalMode.MICROBATCH:
        raise CompileInputError(
            f"model '{model_name}': batch_concurrency is only valid with "
            f"incremental_mode=microbatch"
        )


def _str(config: CompileModelConfig, key: str) -> str | None:
    """Extract a string value from config."""

    raw: object | None = config.values.get(key)
    return raw if isinstance(raw, str) else None
