"""Run-cost execution context."""

from contextlib import AbstractContextManager, nullcontext
from pathlib import Path

from sqlbuild.cost._helpers.context import (
    cost_resource_context,
    current_cost_resource_context,
)
from sqlbuild.cost.models import CostResourceContext


class CostContext:
    @staticmethod
    def current() -> CostResourceContext | None:
        return current_cost_resource_context()

    @staticmethod
    def scope(
        *,
        run_id: str,
        resource_type: str,
        resource_name: str,
        ledger_path: Path | None = None,
        phase: str = "execute",
        attempt: int = 1,
    ) -> AbstractContextManager[None]:
        return cost_resource_context(
            run_id=run_id,
            resource_type=resource_type,
            resource_name=resource_name,
            ledger_path=ledger_path,
            phase=phase,
            attempt=attempt,
        )

    @staticmethod
    def resource_scope(
        *,
        resource_type: str,
        resource_name: str,
        phase: str | None = None,
        attempt: int = 1,
    ) -> AbstractContextManager[None]:
        current: CostResourceContext | None = CostContext.current()
        if current is None:
            return nullcontext()
        return CostContext.scope(
            run_id=current.run_id,
            resource_type=resource_type,
            resource_name=resource_name,
            ledger_path=current.ledger_path,
            phase=current.phase if phase is None else phase,
            attempt=attempt,
        )
