"""Observed DB-API cursor and connection proxies."""

from __future__ import annotations

from types import TracebackType
from typing import Any

from sqlbuild.adapter.contract._helpers.observed_statement import batch_size, statement_is_active
from sqlbuild.runtime.observability.classes.statement_lifecycle import StatementLifecycle

_PROXY_ATTRIBUTES: frozenset[str] = frozenset({"raw_cursor", "adapter", "owner_connection"})


class ObservedCursor:
    """Instrument DB-API execute calls while preserving cursor behavior."""

    def __init__(
        self, *, raw_cursor: Any, adapter: str, owner_connection: Any | None = None
    ) -> None:
        object.__setattr__(self, "raw_cursor", raw_cursor)
        object.__setattr__(self, "adapter", adapter)
        object.__setattr__(self, "owner_connection", owner_connection)

    @property
    def connection(self) -> Any:
        if self.owner_connection is not None:
            return self.owner_connection
        return self.raw_cursor.connection

    def __setattr__(self, name: str, value: Any) -> None:
        if name in _PROXY_ATTRIBUTES:
            object.__setattr__(self, name, value)
            return
        setattr(self.raw_cursor, name, value)

    def execute(self, sql: str, *args: Any, **kwargs: Any) -> Any:
        if statement_is_active():
            result: Any = self.raw_cursor.execute(sql, *args, **kwargs)
            return self if result is self.raw_cursor else result
        with StatementLifecycle(adapter=self.adapter, sql=sql, intent="execute") as lifecycle:
            result = self.raw_cursor.execute(sql, *args, **kwargs)
            lifecycle.completed(affected_rows=_row_count(cursor=self.raw_cursor))
        return self if result is self.raw_cursor else result

    def executemany(self, sql: str, *args: Any, **kwargs: Any) -> Any:
        if statement_is_active():
            result: Any = self.raw_cursor.executemany(sql, *args, **kwargs)
            return self if result is self.raw_cursor else result
        with StatementLifecycle(
            adapter=self.adapter,
            sql=sql,
            intent="executemany",
            batch_size=batch_size(args=args),
        ) as lifecycle:
            result = self.raw_cursor.executemany(sql, *args, **kwargs)
            lifecycle.completed(affected_rows=_row_count(cursor=self.raw_cursor))
        return self if result is self.raw_cursor else result

    def __enter__(self) -> ObservedCursor:
        self.raw_cursor.__enter__()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool | None:
        return self.raw_cursor.__exit__(exc_type, exc_value, traceback)

    def __iter__(self) -> ObservedCursor:
        return self

    def __next__(self) -> Any:
        return next(self.raw_cursor)

    def __getattr__(self, name: str) -> Any:
        return getattr(self.raw_cursor, name)


def _row_count(*, cursor: Any) -> int | None:
    value: object | None = getattr(cursor, "rowcount", None)
    return value if isinstance(value, int) and value >= 0 else None
