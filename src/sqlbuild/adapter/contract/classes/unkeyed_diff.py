"""Reusable exact unkeyed diff implementation for first-class adapters."""

from __future__ import annotations

from typing import Any, cast

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
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
