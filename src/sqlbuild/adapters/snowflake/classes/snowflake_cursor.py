"""Snowflake cursor proxy with non-degrading statement telemetry."""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from types import TracebackType
from typing import Any
from uuid import uuid4

from sqlbuild.cost.classes.cost_context import CostContext
from sqlbuild.cost.classes.statement_ledger import StatementLedger
from sqlbuild.cost.constants import SQLBUILD_QUERY_TAG_APP
from sqlbuild.cost.models import CostResourceContext, StatementExecutionTelemetry
from sqlbuild.runtime.observability.classes.statement_lifecycle import StatementLifecycle
from sqlbuild.runtime.observability.main.current_execution_identity import (
    current_execution_identity,
)
from sqlbuild.runtime.observability.models import ExecutionIdentity

_LOGGER: logging.Logger = logging.getLogger("sqlbuild.cost")
_QUERY_TAG_PARAMETER: str = "QUERY_TAG"
_STATEMENT_PARAMETER_ERROR_FRAGMENT: str = "STATEMENT PARAMETER"
_RAW_CURSOR_ATTRIBUTE: str = "raw_cursor"
_EXECUTEMANY_INTENT: str = "executemany"


def _statement_id() -> str:
    identity: ExecutionIdentity | None = current_execution_identity()
    if identity is not None and identity.statement_id is not None:
        return identity.statement_id
    return uuid4().hex


class _SnowflakeCursor:
    """Delegate cursor operations while tagging and recording executed statements."""

    def __init__(self, raw_cursor: Any) -> None:
        object.__setattr__(self, _RAW_CURSOR_ATTRIBUTE, raw_cursor)

    def __setattr__(self, name: str, value: Any) -> None:
        if name == _RAW_CURSOR_ATTRIBUTE:
            object.__setattr__(self, name, value)
            return
        setattr(self.raw_cursor, name, value)

    def execute(self, sql: str, *args: Any, **kwargs: Any) -> Any:
        context: CostResourceContext | None = CostContext.current()
        statement_id: str = _statement_id()
        tagged_kwargs, query_tag_injected = _with_query_tag(
            kwargs=kwargs, context=context, statement_id=statement_id
        )
        return self._execute_with_telemetry(
            operation=self.raw_cursor.execute,
            sql=sql,
            args=args,
            kwargs=tagged_kwargs,
            context=context,
            statement_id=statement_id,
            query_tag_injected=query_tag_injected,
            intent="execute",
        )

    def executemany(self, sql: str, *args: Any, **kwargs: Any) -> Any:
        context: CostResourceContext | None = CostContext.current()
        statement_id: str = _statement_id()
        tagged_kwargs, query_tag_injected = _with_query_tag(
            kwargs=kwargs, context=context, statement_id=statement_id
        )
        return self._execute_with_telemetry(
            operation=self.raw_cursor.executemany,
            sql=sql,
            args=args,
            kwargs=tagged_kwargs,
            context=context,
            statement_id=statement_id,
            query_tag_injected=query_tag_injected,
            intent=_EXECUTEMANY_INTENT,
        )

    def _execute_with_telemetry(
        self,
        *,
        operation: Callable[..., Any],
        sql: str,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
        context: CostResourceContext | None,
        statement_id: str,
        query_tag_injected: bool,
        intent: str,
    ) -> Any:
        started_at: datetime = datetime.now(UTC)
        started_monotonic: float = time.monotonic()
        previous_query_id: str | None = _current_query_id(cursor=self.raw_cursor)
        batch_size: int | None = _batch_size(args=args) if intent == _EXECUTEMANY_INTENT else None
        with StatementLifecycle(
            adapter="snowflake",
            sql=sql,
            intent=intent,
            batch_size=batch_size,
            statement_id=statement_id,
        ) as lifecycle:
            try:
                result: Any = operation(sql, *args, **kwargs)
            except Exception as error:
                if query_tag_injected and _can_retry_without_query_tag(
                    cursor=self.raw_cursor,
                    error=error,
                    kwargs=kwargs,
                    previous_query_id=previous_query_id,
                ):
                    _LOGGER.warning(
                        "Snowflake query tagging was rejected before submission; "
                        "continuing without a query tag"
                    )
                    retry_kwargs: dict[str, Any] = _without_query_tag(kwargs=kwargs)
                    try:
                        result = operation(sql, *args, **retry_kwargs)
                    except Exception as retry_error:
                        query_id: str | None = self._record_failure(
                            context=context,
                            sql=sql,
                            started_at=started_at,
                            started_monotonic=started_monotonic,
                            error=retry_error,
                            previous_query_id=previous_query_id,
                            statement_id=statement_id,
                        )
                        lifecycle.failed(error=retry_error, query_id=query_id)
                        raise
                    query_id = self._record_success(
                        context=context,
                        sql=sql,
                        started_at=started_at,
                        started_monotonic=started_monotonic,
                        previous_query_id=previous_query_id,
                        statement_id=statement_id,
                    )
                    lifecycle.completed(query_id=query_id)
                    return self if result is self.raw_cursor else result
                query_id = self._record_failure(
                    context=context,
                    sql=sql,
                    started_at=started_at,
                    started_monotonic=started_monotonic,
                    error=error,
                    previous_query_id=previous_query_id,
                    statement_id=statement_id,
                )
                lifecycle.failed(error=error, query_id=query_id)
                raise
            query_id = self._record_success(
                context=context,
                sql=sql,
                started_at=started_at,
                started_monotonic=started_monotonic,
                previous_query_id=previous_query_id,
                statement_id=statement_id,
            )
            lifecycle.completed(query_id=query_id)
            return self if result is self.raw_cursor else result

    def __enter__(self) -> _SnowflakeCursor:
        self.raw_cursor.__enter__()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool | None:
        return self.raw_cursor.__exit__(exc_type, exc_value, traceback)

    def __iter__(self) -> Iterator[Any]:
        return iter(self.raw_cursor)

    def _record_failure(
        self,
        *,
        context: CostResourceContext | None,
        sql: str,
        started_at: datetime,
        started_monotonic: float,
        error: Exception,
        previous_query_id: str | None,
        statement_id: str,
    ) -> str | None:
        completed_at: datetime = datetime.now(UTC)
        elapsed_seconds: float = time.monotonic() - started_monotonic
        query_id: str | None = _submitted_query_id(
            cursor=self.raw_cursor, previous_query_id=previous_query_id
        )
        if context is not None:
            StatementLedger.record(
                context=context,
                statement_id=statement_id,
                sql=sql,
                query_id=query_id,
                status="failed",
                started_at=started_at,
                completed_at=completed_at,
                error=error,
            )
            _notify_statement_complete(
                context=context,
                query_id=query_id,
                status="failed",
                elapsed_seconds=elapsed_seconds,
            )
        return query_id

    def _record_success(
        self,
        *,
        context: CostResourceContext | None,
        sql: str,
        started_at: datetime,
        started_monotonic: float,
        previous_query_id: str | None,
        statement_id: str,
    ) -> str | None:
        completed_at: datetime = datetime.now(UTC)
        elapsed_seconds: float = time.monotonic() - started_monotonic
        query_id: str | None = _submitted_query_id(
            cursor=self.raw_cursor, previous_query_id=previous_query_id
        )
        if context is not None:
            StatementLedger.record(
                context=context,
                statement_id=statement_id,
                sql=sql,
                query_id=query_id,
                status="success",
                started_at=started_at,
                completed_at=completed_at,
            )
            _notify_statement_complete(
                context=context,
                query_id=query_id,
                status="success",
                elapsed_seconds=elapsed_seconds,
            )
        return query_id

    def __getattr__(self, name: str) -> Any:
        return getattr(self.raw_cursor, name)


def _with_query_tag(
    *,
    kwargs: dict[str, Any],
    context: CostResourceContext | None,
    statement_id: str,
) -> tuple[dict[str, Any], bool]:
    tagged_kwargs: dict[str, Any] = dict(kwargs)
    if context is None:
        return tagged_kwargs, False
    statement_params: dict[str, str] = dict(tagged_kwargs.get("_statement_params") or {})
    if _QUERY_TAG_PARAMETER in statement_params:
        return tagged_kwargs, False
    statement_params[_QUERY_TAG_PARAMETER] = json.dumps(
        {
            "app": SQLBUILD_QUERY_TAG_APP,
            "attempt": context.attempt,
            "phase": context.phase,
            "resource_name": context.resource_name,
            "resource_type": context.resource_type,
            "run_id": context.run_id,
            "statement_id": statement_id,
            "v": 1,
        },
        separators=(",", ":"),
        sort_keys=True,
    )
    tagged_kwargs["_statement_params"] = statement_params
    return tagged_kwargs, True


def _without_query_tag(*, kwargs: dict[str, Any]) -> dict[str, Any]:
    retry_kwargs: dict[str, Any] = dict(kwargs)
    statement_params: dict[str, str] = dict(retry_kwargs.get("_statement_params") or {})
    statement_params.pop(_QUERY_TAG_PARAMETER, None)
    if statement_params:
        retry_kwargs["_statement_params"] = statement_params
    else:
        retry_kwargs.pop("_statement_params", None)
    return retry_kwargs


def _can_retry_without_query_tag(
    *,
    cursor: Any,
    error: Exception,
    kwargs: dict[str, Any],
    previous_query_id: str | None,
) -> bool:
    statement_params: object = kwargs.get("_statement_params")
    if not isinstance(statement_params, dict) or _QUERY_TAG_PARAMETER not in statement_params:
        return False
    if _current_query_id(cursor=cursor) != previous_query_id:
        return False
    message: str = str(error).upper()
    return _QUERY_TAG_PARAMETER in message or _STATEMENT_PARAMETER_ERROR_FRAGMENT in message


def _submitted_query_id(*, cursor: Any, previous_query_id: str | None) -> str | None:
    current_query_id: str | None = _current_query_id(cursor=cursor)
    return current_query_id if current_query_id != previous_query_id else None


def _current_query_id(*, cursor: Any) -> str | None:
    query_id: object = getattr(cursor, "sfqid", None)
    return query_id if isinstance(query_id, str) and query_id else None


def _batch_size(*, args: tuple[Any, ...]) -> int | None:
    if not args or not isinstance(args[0], (list, tuple)):
        return None
    return len(args[0])


def _notify_statement_complete(
    *,
    context: CostResourceContext,
    query_id: str | None,
    status: str,
    elapsed_seconds: float,
) -> None:
    callback: Callable[[StatementExecutionTelemetry], None] | None = context.on_statement_complete
    if callback is None:
        return
    try:
        callback(
            StatementExecutionTelemetry(
                query_id=query_id,
                status=status,
                elapsed_seconds=elapsed_seconds,
                resource_type=context.resource_type,
                resource_name=context.resource_name,
                phase=context.phase,
            )
        )
    except BaseException:
        _LOGGER.exception("Snowflake statement completion diagnostics failed")
