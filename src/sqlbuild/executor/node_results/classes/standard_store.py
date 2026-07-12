"""Standard-mode runtime node result store."""

from __future__ import annotations

from typing import Any

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.adapter.shared.models import StatementRecorder
from sqlbuild.executor.node_results.main.read import read_node_results
from sqlbuild.executor.node_results.main.write import write_node_result_record
from sqlbuild.executor.node_results.models import (
    NodeResultEnvelope,
    NodeResultQuery,
    NodeResultRecord,
)
from sqlbuild.executor.node_results.types import NodeResultStatus
from sqlbuild.executor.python_nodes.constants import MISSING_DEFAULT
from sqlbuild.executor.shared.exceptions import ExecutorInputError


class StandardNodeResultStore:
    """Warehouse-backed node result store for standard-mode execution."""

    def __init__(
        self,
        *,
        adapter: BaseAdapter,
        connection: Any,
        database: str | None,
        schema: str | None,
    ) -> None:
        self.adapter: BaseAdapter = adapter
        self.connection: Any = connection
        self.database: str | None = database
        self.schema: str | None = schema
        self._cached_results: list[NodeResultEnvelope] = []

    def write(self, record: NodeResultRecord) -> None:
        if self.schema is None:
            return
        self.adapter.ensure_schema(
            connection=self.connection,
            database=self.database,
            schema=self.schema,
            statement_recorder=StatementRecorder(),
        )
        write_node_result_record(
            connection=self.connection,
            execute=self.adapter.execute,
            database=self.database,
            schema=self.schema,
            record=record,
            render_qualified_name=self.adapter.render_qualified_name,
            render_framework_type=self.adapter.render_framework_type,
            render_create_table_sql=self.adapter.render_create_node_result_table_sql,
            render_create_index_sqls=self.adapter.render_create_node_result_index_sqls,
        )
        self._cached_results.insert(0, self._record_to_envelope(record))

    def result_of(
        self,
        *,
        node_type: str,
        node_name: str,
        run_id: str | None = None,
        default: object = MISSING_DEFAULT,
    ) -> NodeResultEnvelope | object:
        result: NodeResultEnvelope | None = self._read_cached_one(
            node_type=node_type,
            node_name=node_name,
            run_id=run_id,
        ) or self._read_one(node_type=node_type, node_name=node_name, run_id=run_id)
        if result is not None:
            return result
        if default is not MISSING_DEFAULT:
            return default
        raise ExecutorInputError(f"No persisted result found for Python node '{node_name}'")

    def results_of(
        self,
        *,
        node_type: str,
        node_name: str,
        limit: int,
    ) -> tuple[NodeResultEnvelope, ...]:
        if self.schema is None:
            return ()
        cached_results: tuple[NodeResultEnvelope, ...] = self._read_cached_history(
            node_type=node_type,
            node_name=node_name,
            limit=limit,
        )
        if len(cached_results) >= limit:
            return cached_results
        return read_node_results(
            connection=self.connection,
            execute=self.adapter.execute,
            relation_exists=self.adapter.relation_exists,
            database=self.database,
            schema=self.schema,
            query=NodeResultQuery(
                node_type=node_type,
                node_name=node_name,
                target_database=self.database,
                target_schema=self.schema,
                target_name=None,
                statuses=(NodeResultStatus.SUCCESS.value,),
                run_id=None,
                limit=limit,
            ),
            render_qualified_name=self.adapter.render_qualified_name,
        )

    def _read_one(
        self,
        *,
        node_type: str,
        node_name: str,
        run_id: str | None,
    ) -> NodeResultEnvelope | None:
        if self.schema is None:
            return None
        results: tuple[NodeResultEnvelope, ...] = read_node_results(
            connection=self.connection,
            execute=self.adapter.execute,
            relation_exists=self.adapter.relation_exists,
            database=self.database,
            schema=self.schema,
            query=NodeResultQuery(
                node_type=node_type,
                node_name=node_name,
                target_database=self.database,
                target_schema=self.schema,
                target_name=None,
                statuses=None if run_id is not None else (NodeResultStatus.SUCCESS.value,),
                run_id=run_id,
                limit=1,
            ),
            render_qualified_name=self.adapter.render_qualified_name,
        )
        return results[0] if results else None

    def _read_cached_one(
        self,
        *,
        node_type: str,
        node_name: str,
        run_id: str | None,
    ) -> NodeResultEnvelope | None:
        result: NodeResultEnvelope
        for result in self._cached_results:
            if result.node_type != node_type or result.node_name != node_name:
                continue
            if run_id is not None and result.run_id != run_id:
                continue
            if run_id is None and result.status != NodeResultStatus.SUCCESS.value:
                continue
            return result
        return None

    def _read_cached_history(
        self,
        *,
        node_type: str,
        node_name: str,
        limit: int,
    ) -> tuple[NodeResultEnvelope, ...]:
        results: list[NodeResultEnvelope] = []
        result: NodeResultEnvelope
        for result in self._cached_results:
            if result.node_type != node_type or result.node_name != node_name:
                continue
            if result.status != NodeResultStatus.SUCCESS.value:
                continue
            results.append(result)
            if len(results) >= limit:
                break
        return tuple(results)

    def _record_to_envelope(self, record: NodeResultRecord) -> NodeResultEnvelope:
        return NodeResultEnvelope(
            node_type=record.node_type,
            node_name=record.node_name,
            run_id=record.run_id,
            status=record.status,
            payload=record.payload,
            metadata=record.metadata,
            error_message=record.error_message,
            materialized=record.materialized,
            ts=record.ts,
        )
