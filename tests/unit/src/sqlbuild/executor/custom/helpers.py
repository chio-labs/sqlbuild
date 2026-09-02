from __future__ import annotations

import logging
from typing import Any, ClassVar

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.adapter.contract.classes.statement_recorder import StatementRecorder
from sqlbuild.executor.auditing.models import AuditExecutionResult
from sqlbuild.executor.custom.models import MaterializationContext, PrepareVersionContext


class RecordingCustomAdapter(BaseAdapter):
    adapter_name: ClassVar[str] = "custom-test"

    def __init__(self, *, operation_order: list[str], execute_result: object) -> None:
        self.operation_order = operation_order
        self.execute_result = execute_result
        self.executed_connection: object | None = None
        self.executed_sql: str | None = None

    def connect(self, config: dict[str, object]) -> object:
        del config
        return object()

    def close(self, connection: object) -> None:
        del connection

    def _execute(self, connection: Any, sql: str) -> object:
        self.operation_order.append("execute")
        self.executed_connection = connection
        self.executed_sql = sql
        return self.execute_result


class OrderingStatementRecorder(StatementRecorder):
    def __init__(self, *, operation_order: list[str]) -> None:
        super().__init__()
        self.operation_order = operation_order

    def record(self, statement: str) -> None:
        self.operation_order.append("record")
        super().record(statement)


def _empty_audit_results(relation: str) -> tuple[AuditExecutionResult, ...]:
    del relation
    return ()


def build_materialization_context(
    *,
    adapter: BaseAdapter,
    connection: object,
    statement_recorder: StatementRecorder,
) -> MaterializationContext:
    return MaterializationContext(
        adapter=adapter,
        connection=connection,
        destination="warehouse.analytics.orders",
        destination_database="warehouse",
        destination_schema="analytics",
        destination_name="orders",
        sql="SELECT 1",
        config={},
        placeholders={},
        existing_relation=None,
        run_id="test-run",
        build_target="dev",
        vars={},
        unique_key=(),
        declared_columns=(),
        is_first_run=True,
        is_full_refresh=False,
        query_changed=False,
        schema_findings=(),
        run_audits=_empty_audit_results,
        on_progress=None,
        logger=logging.getLogger(__name__),
        statement_recorder=statement_recorder,
    )


def build_prepare_version_context(
    *,
    adapter: BaseAdapter,
    connection: object,
    statement_recorder: StatementRecorder,
) -> PrepareVersionContext:
    return PrepareVersionContext(
        adapter=adapter,
        connection=connection,
        origin_relation="warehouse.analytics.orders_origin",
        destination="warehouse.analytics.orders",
        destination_database="warehouse",
        destination_schema="analytics",
        destination_name="orders",
        config={},
        placeholders={},
        run_id="test-run",
        environment="dev",
        vars={},
        unique_key=(),
        declared_columns=(),
        statement_recorder=statement_recorder,
    )
