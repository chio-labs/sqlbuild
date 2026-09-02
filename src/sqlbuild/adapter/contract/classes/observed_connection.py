"""Observed DB-API connection proxy."""

from __future__ import annotations

from types import TracebackType
from typing import Any

from sqlbuild.adapter.contract._helpers.observed_statement import batch_size, statement_is_active
from sqlbuild.adapter.contract.classes.observed_cursor import ObservedCursor
from sqlbuild.runtime.observability.classes.statement_lifecycle import StatementLifecycle

_PROXY_ATTRIBUTES: frozenset[str] = frozenset({"raw_connection", "adapter"})


class ObservedConnection:
    """Instrument direct connection execution and cursors at one driver boundary."""

    def __init__(self, *, raw_connection: Any, adapter: str) -> None:
        object.__setattr__(self, "raw_connection", raw_connection)
        object.__setattr__(self, "adapter", adapter)

    def __setattr__(self, name: str, value: Any) -> None:
        if name in _PROXY_ATTRIBUTES:
            object.__setattr__(self, name, value)
            return
        setattr(self.raw_connection, name, value)

    def execute(self, sql: str, *args: Any, **kwargs: Any) -> Any:
        if statement_is_active():
            result: Any = self.raw_connection.execute(sql, *args, **kwargs)
            return self if result is self.raw_connection else result
        with StatementLifecycle(adapter=self.adapter, sql=sql, intent="execute") as lifecycle:
            result = self.raw_connection.execute(sql, *args, **kwargs)
            lifecycle.completed(affected_rows=_row_count(cursor=result))
        return self if result is self.raw_connection else result

    def executemany(self, sql: str, *args: Any, **kwargs: Any) -> Any:
        if statement_is_active():
            result: Any = self.raw_connection.executemany(sql, *args, **kwargs)
            return self if result is self.raw_connection else result
        with StatementLifecycle(
            adapter=self.adapter,
            sql=sql,
            intent="executemany",
            batch_size=batch_size(args=args),
        ) as lifecycle:
            result = self.raw_connection.executemany(sql, *args, **kwargs)
            lifecycle.completed(affected_rows=_row_count(cursor=result))
        return self if result is self.raw_connection else result

    def cursor(self, *args: Any, **kwargs: Any) -> ObservedCursor:
        return ObservedCursor(
            raw_cursor=self.raw_connection.cursor(*args, **kwargs),
            adapter=self.adapter,
            owner_connection=self,
        )

    def __enter__(self) -> ObservedConnection:
        self.raw_connection.__enter__()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool | None:
        return self.raw_connection.__exit__(exc_type, exc_value, traceback)

    def __iter__(self) -> ObservedConnection:
        return self

    def __next__(self) -> Any:
        row: Any | None = self.raw_connection.fetchone()
        if row is None:
            return next(iter(()))
        return row

    def __getattr__(self, name: str) -> Any:
        return getattr(self.raw_connection, name)


def _row_count(*, cursor: Any) -> int | None:
    value: object | None = getattr(cursor, "rowcount", None)
    return value if isinstance(value, int) and value >= 0 else None
