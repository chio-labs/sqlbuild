"""Reusable exact unkeyed diff implementation for first-class adapters."""

from __future__ import annotations

from typing import Any, cast

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.adapter.contract.constants import DIFF_LEFT_SIDE
from sqlbuild.adapter.contract.models import CursorValue, RowDiffResult


class UnkeyedDiffMixin:
    """Expose shared multiset comparison below the base contract boundary."""

    def diff_unkeyed_rows(
        self,
        *,
        connection: Any,
        left: str,
        right: str,
        excluded_columns: tuple[str, ...] = (),
        cursor_column: str | None = None,
        start_cursor: CursorValue | None = None,
        end_cursor: CursorValue | None = None,
    ) -> RowDiffResult:
        """Compare exact full-row multiplicities without a unique key."""

        return BaseAdapter.diff_unkeyed_rows(
            cast(BaseAdapter, self),
            connection=connection,
            left=left,
            right=right,
            excluded_columns=excluded_columns,
            cursor_column=cursor_column,
            start_cursor=start_cursor,
            end_cursor=end_cursor,
        )

    def sample_unkeyed_side_only_rows(
        self,
        *,
        connection: Any,
        left: str,
        right: str,
        side: str,
        excluded_columns: tuple[str, ...] = (),
        cursor_column: str | None = None,
        start_cursor: CursorValue | None = None,
        end_cursor: CursorValue | None = None,
        limit: int = 20,
    ) -> tuple[tuple[tuple[str, object], ...], ...]:
        """Return up to ``limit`` complete rows one side holds more often than the other."""

        if limit <= 0:
            return ()
        columns, joined_sql = BaseAdapter._unkeyed_multiset_sql(
            cast(BaseAdapter, self),
            connection=connection,
            left=left,
            right=right,
            excluded_columns=excluded_columns,
            cursor_column=cursor_column,
            start_cursor=start_cursor,
            end_cursor=end_cursor,
            carried_side=side,
        )
        surplus: str = (
            "__left_count - __right_count"
            if side == DIFF_LEFT_SIDE
            else "__right_count - __left_count"
        )
        names: str = ", ".join(f"__c{index}" for index in range(len(columns)))
        sql: str = self._render_unkeyed_sample_sql(
            joined_sql=joined_sql,
            select_list=f"{names}, {surplus}",
            predicate=f"{surplus} > 0",
            limit=limit,
        )
        cursor: Any = cast(BaseAdapter, self).execute(connection=connection, sql=sql)
        try:
            fetched_rows: list[Any] = cursor.fetchall()
        finally:
            if cursor is not connection:
                cursor.close()
        rows: list[tuple[tuple[str, object], ...]] = []
        for fetched in fetched_rows:
            values: tuple[Any, ...] = tuple(fetched)
            row: tuple[tuple[str, object], ...] = tuple(
                (column.name, value) for column, value in zip(columns, values[:-1], strict=True)
            )
            rows.extend([row] * min(int(values[-1]), limit - len(rows)))
            if len(rows) >= limit:
                break
        return tuple(rows)

    def _render_unkeyed_sample_sql(
        self, *, joined_sql: str, select_list: str, predicate: str, limit: int
    ) -> str:
        """Render the bounded side-only sample query for LIMIT-capable engines."""

        return f"{joined_sql} SELECT {select_list} FROM __joined WHERE {predicate} LIMIT {limit}"
