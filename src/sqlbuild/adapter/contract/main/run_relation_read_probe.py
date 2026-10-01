"""Direct relation read probe shared by adapter contract implementations."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from sqlbuild.adapter.contract.models import RelationReadProbe
from sqlbuild.adapter.contract.types import AdapterExecute, RelationReadStatus


def run_relation_read_probe(
    *,
    execute: AdapterExecute[Any, Any],
    connection: Any,
    relation: str,
    classify_not_found: Callable[[BaseException], RelationReadStatus | None],
) -> RelationReadProbe:
    """Read nothing from a relation; only adapter-classified not-found errors become outcomes."""

    try:
        cursor: object = execute(connection=connection, sql=f"SELECT 1 FROM {relation} WHERE 1=0")
    except Exception as error:
        link: BaseException
        for link in _error_chain(error):
            status: RelationReadStatus | None = classify_not_found(link)
            if status is not None:
                return RelationReadProbe(status=status)
        raise
    del cursor
    return RelationReadProbe(status=RelationReadStatus.READABLE)


def _error_chain(error: BaseException) -> tuple[BaseException, ...]:
    chain: list[BaseException] = []
    pending: list[BaseException] = [error]
    while pending:
        current: BaseException = pending.pop()
        if any(current is seen for seen in chain):
            continue
        chain.append(current)
        original: object = getattr(current, "__dict__", {}).get("original_error")
        pending.extend(
            link
            for link in (current.__cause__, current.__context__, original)
            if isinstance(link, BaseException)
        )
    return tuple(chain)
