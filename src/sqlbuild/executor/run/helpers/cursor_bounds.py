"""Runtime cursor bound resolution and sentinel substitution."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.compiler.planner.constants import MICROBATCH_END_SENTINEL, MICROBATCH_START_SENTINEL
from sqlbuild.compiler.planner.models import CursorBounds, CursorInputRelation


def has_model_backed_cursor_inputs(
    cursor_input_relations: tuple[CursorInputRelation, ...],
) -> bool:
    """Return whether any cursor input relation is backed by another model."""

    return any(relation.is_model_backed for relation in cursor_input_relations)


def resolve_runtime_cursor_bounds(
    *,
    adapter: BaseAdapter,
    connection: Any,
    target_relation: str,
    cursor_column: str,
    cursor_input_relations: tuple[CursorInputRelation, ...],
) -> CursorBounds | None:
    """Resolve concrete runtime cursor bounds from target and upstream relations."""

    upstream_parts: list[str] = []
    cursor_input: CursorInputRelation
    for cursor_input in cursor_input_relations:
        upstream_parts.append(
            f"SELECT MIN({cursor_input.cursor_column}) AS _min, "
            f"MAX({cursor_input.cursor_column}) AS _max FROM {cursor_input.relation}"
        )
    if not upstream_parts:
        return None

    target_max: str | None = _query_target_max(
        adapter=adapter,
        connection=connection,
        target_relation=target_relation,
        cursor_column=cursor_column,
    )
    sql: str = "SELECT MIN(_min), MAX(_max) FROM (" + " UNION ALL ".join(upstream_parts) + ")"
    cursor: Any = adapter.execute(connection, sql)
    row: Any = cursor.fetchone()
    if row is None or row[1] is None:
        return None

    start: str | None = (
        target_max if target_max is not None else _normalize_bound(row[0], is_end=False)
    )
    end: str | None = _normalize_bound(row[1], is_end=True)
    if start is None or end is None:
        return None
    return CursorBounds(start=start, end=end)


def substitute_cursor_sentinels(*, sql: str, bounds: CursorBounds) -> str:
    """Substitute runtime cursor sentinels with concrete bounds."""

    result: str = sql.replace(MICROBATCH_START_SENTINEL, bounds.start)
    return result.replace(MICROBATCH_END_SENTINEL, bounds.end)


def _query_target_max(
    *,
    adapter: BaseAdapter,
    connection: Any,
    target_relation: str,
    cursor_column: str,
) -> str | None:
    sql: str = f"SELECT MAX({cursor_column}) FROM {target_relation}"
    try:
        cursor: Any = adapter.execute(connection, sql)
    except Exception:
        return None
    row: Any = cursor.fetchone()
    if row is None or row[0] is None:
        return None
    return _normalize_bound(row[0], is_end=False)


def _normalize_bound(value: object, *, is_end: bool) -> str | None:
    if isinstance(value, datetime):
        normalized: datetime = value + timedelta(seconds=1) if is_end else value
        return normalized.isoformat()
    if isinstance(value, int):
        normalized_int: int = value + 1 if is_end else value
        return str(normalized_int)
    if value is None:
        return None
    return str(value)
