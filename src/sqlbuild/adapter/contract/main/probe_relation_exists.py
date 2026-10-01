"""Direct relation existence probe shared by adapter contract implementations."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from sqlbuild.adapter.contract.types import AdapterExecute


def probe_relation_exists(
    *,
    execute: AdapterExecute[Any, Any],
    connection: Any,
    relation: str,
    is_not_found: Callable[[BaseException], bool],
    probe_sql: str | None = None,
) -> bool:
    """Return False only when reading the relation fails with an object-not-found error."""

    try:
        cursor: object = execute(
            connection=connection, sql=probe_sql or f"SELECT 1 FROM {relation} WHERE 1=0"
        )
    except Exception as error:
        if any(is_not_found(link) for link in _error_chain(error)):
            return False
        raise
    del cursor
    return True


def _error_chain(error: BaseException) -> tuple[BaseException, ...]:
    chain: list[BaseException] = []
    pending: list[BaseException] = [error]
    while pending:
        current: BaseException = pending.pop()
        if any(current is seen for seen in chain):
            continue
        chain.append(current)
        original: object = (
            vars(current).get("original_error") if hasattr(current, "__dict__") else None
        )
        pending.extend(
            link
            for link in (current.__cause__, current.__context__, original)
            if isinstance(link, BaseException)
        )
    return tuple(chain)
