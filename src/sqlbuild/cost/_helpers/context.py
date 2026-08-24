"""Per-resource cost attribution context."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar, Token
from pathlib import Path

from sqlbuild.cost.models import CostResourceContext

_CURRENT: ContextVar[CostResourceContext | None] = ContextVar(
    "sqlbuild_cost_resource_context", default=None
)


def current_cost_resource_context() -> CostResourceContext | None:
    return _CURRENT.get()


@contextmanager
def cost_resource_context(
    *,
    run_id: str,
    resource_type: str,
    resource_name: str,
    ledger_path: Path | None = None,
    phase: str = "execute",
    attempt: int = 1,
) -> Iterator[None]:
    token: Token[CostResourceContext | None] = _CURRENT.set(
        CostResourceContext(
            run_id=run_id,
            resource_type=resource_type,
            resource_name=resource_name,
            ledger_path=ledger_path,
            phase=phase,
            attempt=attempt,
        )
    )
    try:
        yield
    finally:
        _CURRENT.reset(token)
