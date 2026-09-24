"""Cursor windows rendered for models that SQL tests evaluate from their real SQL."""

from __future__ import annotations

from dataclasses import dataclass

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.compiler.compile.exceptions import CompileInputError
from sqlbuild.compiler.compile.main.cursor_intrinsics import resolve_cursor_intrinsics
from sqlbuild.compiler.compile.models import CompiledModel, CompiledSqlTest
from sqlbuild.compiler.planner.types import CursorGrain, CursorType
from sqlbuild.cursor_algebra.exceptions import CursorAlgebraError
from sqlbuild.cursor_algebra.main.compare import compare
from sqlbuild.cursor_algebra.main.floor_to_grain import floor_to_grain
from sqlbuild.cursor_algebra.main.parse import parse
from sqlbuild.cursor_algebra.main.render import render
from sqlbuild.cursor_algebra.types import CursorScalar
from sqlbuild.spec.contracts.main.get_config_str import get_config_str

_DEFAULT_TIMESTAMP_START: str = "1900-01-01 00:00:00"
_DEFAULT_TIMESTAMP_END: str = "2999-12-31 00:00:00"
_DEFAULT_INTEGER_START: str = "-1000000000000000"
_DEFAULT_INTEGER_END: str = "1000000000000000"
_CURSOR_START_KEY: str = "cursor_start"
_CURSOR_END_KEY: str = "cursor_end"


@dataclass(frozen=True)
class _ModelCursor:
    name: str
    cursor_type: CursorType
    cursor_grain: CursorGrain | None


def uses_cursor_intrinsics(*, sql: str) -> bool:
    """Return whether SQL calls `__cursor_start()` or `__cursor_end()`."""

    _, found = resolve_cursor_intrinsics(sql=sql)
    return found


def declares_cursor_window(*, test: CompiledSqlTest) -> bool:
    """Return whether a SQL test header declares its own cursor window."""

    return test.test_block.cursor_start is not None or test.test_block.cursor_end is not None


def render_test_cursor_intrinsics(
    *,
    sql: str,
    model: CompiledModel,
    adapter: BaseAdapter,
    test: CompiledSqlTest | None,
) -> str:
    """Render cursor intrinsics with the test's declared window, or the wide default window."""

    if not uses_cursor_intrinsics(sql=sql):
        return sql
    cursor: _ModelCursor = _model_cursor(model=model)
    start, end = _test_window(cursor=cursor, test=test)
    rendered, _ = resolve_cursor_intrinsics(
        sql=sql,
        start_sql=adapter.render_cursor_bound_literal(
            value=render(value=start), cursor_type=cursor.cursor_type
        ),
        end_sql=adapter.render_cursor_bound_literal(
            value=render(value=end), cursor_type=cursor.cursor_type
        ),
    )
    return rendered


def declared_window_cursor_models(
    *, test: CompiledSqlTest, chain_models: tuple[CompiledModel, ...]
) -> tuple[CompiledModel, ...]:
    """Validate a declared window against every chain model using intrinsics and return them."""

    cursor_models: tuple[CompiledModel, ...] = tuple(
        model for model in chain_models if uses_cursor_intrinsics(sql=model.query_sql)
    )
    if not cursor_models:
        raise CompileInputError(
            f"{_test_label(test=test)} declares cursor_start or cursor_end, but no model it "
            "evaluates uses __cursor_start() or __cursor_end()"
        )
    for model in cursor_models:
        _test_window(cursor=_model_cursor(model=model), test=test)
    return cursor_models


def _test_window(
    *, cursor: _ModelCursor, test: CompiledSqlTest | None
) -> tuple[CursorScalar, CursorScalar]:
    declared_start: str | None = test.test_block.cursor_start if test is not None else None
    declared_end: str | None = test.test_block.cursor_end if test is not None else None
    integer: bool = cursor.cursor_type == CursorType.INTEGER
    start: CursorScalar = _bound(
        raw=declared_start,
        default=_DEFAULT_INTEGER_START if integer else _DEFAULT_TIMESTAMP_START,
        key=_CURSOR_START_KEY,
        cursor=cursor,
        test=test,
    )
    end: CursorScalar = _bound(
        raw=declared_end,
        default=_DEFAULT_INTEGER_END if integer else _DEFAULT_TIMESTAMP_END,
        key=_CURSOR_END_KEY,
        cursor=cursor,
        test=test,
    )
    if test is not None and compare(left=start, right=end) >= 0:
        raise CompileInputError(
            f"{_test_label(test=test)}: cursor_start '{render(value=start)}' must be before "
            f"the exclusive cursor_end '{render(value=end)}' for model '{cursor.name}'"
        )
    return start, end


def _bound(
    *,
    raw: str | None,
    default: str,
    key: str,
    cursor: _ModelCursor,
    test: CompiledSqlTest | None,
) -> CursorScalar:
    if raw is None or test is None:
        return parse(raw=default, cursor_type=cursor.cursor_type)
    try:
        value: CursorScalar = parse(raw=raw, cursor_type=cursor.cursor_type)
    except CursorAlgebraError:
        expected: str = (
            "an integer" if cursor.cursor_type == CursorType.INTEGER else "an ISO timestamp or date"
        )
        raise CompileInputError(
            f"{_test_label(test=test)}: {key} '{raw}' must be {expected} because model "
            f"'{cursor.name}' uses cursor_type {cursor.cursor_type.value}"
        ) from None
    if cursor.cursor_grain is not None and compare(
        left=floor_to_grain(value=value, grain=cursor.cursor_grain), right=value
    ):
        raise CompileInputError(
            f"{_test_label(test=test)}: {key} '{raw}' is not aligned to cursor_grain "
            f"{cursor.cursor_grain.value} of model '{cursor.name}'"
        )
    return value


def _model_cursor(*, model: CompiledModel) -> _ModelCursor:
    cursor_type: CursorType = CursorType(
        get_config_str(values=model.config.values, key="cursor_type") or CursorType.TIMESTAMP
    )
    grain: str | None = get_config_str(values=model.config.values, key="cursor_grain")
    return _ModelCursor(
        name=model.name,
        cursor_type=cursor_type,
        cursor_grain=(
            CursorGrain(grain)
            if grain is not None and cursor_type == CursorType.TIMESTAMP
            else None
        ),
    )


def _test_label(*, test: CompiledSqlTest) -> str:
    return f"SQL test '{test.name}' in '{test.test_file.relative_path}'"
