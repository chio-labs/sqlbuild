"""Best-effort statement ledger."""

from datetime import datetime

from sqlbuild.cost._helpers.ledger import record_statement
from sqlbuild.cost.models import CostResourceContext


class StatementLedger:
    @staticmethod
    def record(
        *,
        context: CostResourceContext,
        statement_id: str,
        sql: str,
        query_id: object,
        status: str,
        started_at: datetime,
        completed_at: datetime,
        error: Exception | None = None,
    ) -> None:
        record_statement(
            context=context,
            statement_id=statement_id,
            sql=sql,
            query_id=query_id,
            status=status,
            started_at=started_at,
            completed_at=completed_at,
            error=error,
        )
