"""Cursor override typing and native cursor-window exports."""

from __future__ import annotations

import re
from collections.abc import Iterable

from sqlbuild._native import (
    apply_typed_cursor_replay_policy as apply_typed_cursor_replay_policy,
)
from sqlbuild._native import (
    compute_cursor_bounds as compute_cursor_bounds,
)
from sqlbuild._native import (
    cursor_inputs_without_rows as cursor_inputs_without_rows,
)
from sqlbuild._native import (
    cursor_window_override_flags as cursor_window_override_flags,
)
from sqlbuild._native import (
    decide_empty_cursor_inputs as decide_empty_cursor_inputs,
)
from sqlbuild._native import (
    empty_cursor_window as empty_cursor_window,
)
from sqlbuild._native import (
    empty_input_rebuild_refusal as empty_input_rebuild_refusal,
)
from sqlbuild._native import (
    get_config_str,
)
from sqlbuild._native import (
    normalize_cursor_snapshot_grain as normalize_cursor_snapshot_grain,
)
from sqlbuild._native import (
    resolve_effective_timestamp_grain as resolve_effective_timestamp_grain,
)
from sqlbuild._native import (
    unreadable_cursor_inputs_error as unreadable_cursor_inputs_error,
)
from sqlbuild._native import (
    without_destination_cursor as without_destination_cursor,
)
from sqlbuild.compiler.compile.types import CompiledModelView
from sqlbuild.compiler.planner.exceptions import PlannerInputError
from sqlbuild.compiler.planner.models import CursorOverrides
from sqlbuild.compiler.planner.types import CursorType, MaterializationType

_INTEGER_LITERAL: re.Pattern[str] = re.compile(r"[+-]?\d+")
_LISTED_MODEL_LIMIT: int = 3


def type_cursor_overrides(
    *,
    cursor_overrides: CursorOverrides | None,
    selected_models: Iterable[CompiledModelView],
) -> CursorOverrides | None:
    """Type `--start-cursor`/`--end-cursor` from the selected cursor models, else the literal."""

    if cursor_overrides is None or not cursor_overrides.has_untyped:
        return cursor_overrides
    model_names_by_type: dict[CursorType, list[str]] = {}
    model: CompiledModelView
    for model in selected_models:
        cursor_type: CursorType | None = _model_cursor_type(model=model)
        if cursor_type is not None:
            model_names_by_type.setdefault(cursor_type, []).append(model.name)
    if len(model_names_by_type) > 1:
        raise PlannerInputError(
            "--start-cursor and --end-cursor need one cursor type, but the selection mixes "
            + " and ".join(
                f"{cursor_type} cursor models ({_format_names(names)})"
                for cursor_type, names in sorted(model_names_by_type.items())
            ),
            code="S303",
            help=(
                "select models with one cursor type, or set each type explicitly with "
                "--start-cursor-ts/--end-cursor-ts and --start-cursor-int/--end-cursor-int"
            ),
        )
    resolved_type: CursorType = (
        next(iter(model_names_by_type))
        if model_names_by_type
        else _literal_cursor_type(cursor_overrides=cursor_overrides)
    )
    return cursor_overrides.typed_as(cursor_type=resolved_type)


def _model_cursor_type(*, model: CompiledModelView) -> CursorType | None:
    materialized: str | None = get_config_str(values=model.config.values, key="materialized")
    cursor_column: str | None = get_config_str(values=model.config.values, key="cursor")
    if materialized != MaterializationType.INCREMENTAL or cursor_column is None:
        return None
    cursor_type: str | None = get_config_str(values=model.config.values, key="cursor_type")
    if cursor_type not in {CursorType.TIMESTAMP, CursorType.INTEGER}:
        return None
    return CursorType(cursor_type)


def _literal_cursor_type(*, cursor_overrides: CursorOverrides) -> CursorType:
    values: tuple[str, ...] = tuple(
        value for value in (cursor_overrides.start, cursor_overrides.end) if value is not None
    )
    if all(_INTEGER_LITERAL.fullmatch(value.strip()) for value in values):
        return CursorType.INTEGER
    return CursorType.TIMESTAMP


def _format_names(names: list[str]) -> str:
    ordered: list[str] = sorted(names)
    shown: str = ", ".join(ordered[:_LISTED_MODEL_LIMIT])
    hidden: int = len(ordered) - _LISTED_MODEL_LIMIT
    return f"{shown} and {hidden} more" if hidden > 0 else shown
