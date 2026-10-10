"""Recognition and rendering for model cursor-bound SQL intrinsics."""

from __future__ import annotations

import sys
import unicodedata

import sqlbuild._native as _native
from sqlbuild.compiler.compile.exceptions import CompileInputError
from sqlbuild.compiler.frontier.main.report_native_answer import report_native_answer
from sqlbuild.compiler.frontier.types import NativeStage
from sqlbuild.compiler.planner.constants import (
    MICROBATCH_END_SENTINEL,
    MICROBATCH_START_SENTINEL,
)
from sqlbuild.compiler.planner.types import CursorType

_RESERVED_MARKERS: list[str] = [MICROBATCH_START_SENTINEL, MICROBATCH_END_SENTINEL]
_PYTHON: tuple[tuple[int, int], str] = (
    (sys.version_info[0], sys.version_info[1]),
    unicodedata.unidata_version,
)
_CURSOR_START_CALL: str = "__cursor_start()"
_CURSOR_END_CALL: str = "__cursor_end()"


def get_validated_model_cursor_intrinsics(
    *, sql: str, config_values: dict[str, object], model_name: str
) -> str:
    """Validate and canonicalize intrinsics in one model query."""

    canonical_sql, error = _native.validated_model_cursor_intrinsics(
        sql,
        _RESERVED_MARKERS,
        (model_name, config_values.get("materialized"), config_values.get("cursor")),
        _PYTHON,
    )
    report_native_answer(stage=NativeStage.MODEL_LOOP, kind="cursor_intrinsic_validations")
    if error is not None:
        raise CompileInputError(error)
    return str(canonical_sql)


def reject_cursor_intrinsics(*, sql: str, context: str) -> None:
    """Reject cursor intrinsics in SQL that does not own an execution interval."""

    error: str | None = _native.cursor_intrinsics_rejection(
        sql, _RESERVED_MARKERS, context, _PYTHON
    )
    report_native_answer(stage=NativeStage.ATTACHMENTS, kind="cursor_intrinsic_rejections")
    if error is not None:
        raise CompileInputError(error)


def render_cursor_intrinsics(*, sql: str, start_sql: str, end_sql: str) -> str:
    """Render recognized intrinsics to complete adapter-specific bound expressions."""

    rendered, _ = _replaced(sql=sql, context="Model SQL", start_sql=start_sql, end_sql=end_sql)
    return rendered


def cursor_intrinsics_analysis_sql(*, sql: str, cursor_type: object) -> str:
    """Replace intrinsics with stable typed literals only for static SQL analysis."""

    literal: str = (
        "CAST(0 AS BIGINT)"
        if cursor_type == CursorType.INTEGER
        else "CAST('2000-01-01 00:00:00' AS TIMESTAMP)"
    )
    return render_cursor_intrinsics(sql=sql, start_sql=literal, end_sql=literal)


def has_cursor_intrinsics(sql: str) -> bool:
    """Return whether executable SQL contains either cursor intrinsic."""

    _, found = _replaced(
        sql=sql, context="SQL", start_sql=_CURSOR_START_CALL, end_sql=_CURSOR_END_CALL
    )
    return found


def _replaced(*, sql: str, context: str, start_sql: str, end_sql: str) -> tuple[str, bool]:
    replaced, found, error = _native.replace_cursor_intrinsics(
        sql, context, (start_sql, end_sql), _PYTHON
    )
    if error is not None:
        raise CompileInputError(error)
    return replaced, found
