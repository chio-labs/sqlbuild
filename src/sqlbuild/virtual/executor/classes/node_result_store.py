"""VDE state-backed runtime node result store."""

from __future__ import annotations

from typing import Any

from sqlbuild.executor.node_results.classes.node_result_store import NodeResultStore
from sqlbuild.executor.node_results.models import (
    NodeResultEnvelope,
    NodeResultQuery,
    NodeResultRecord,
)
from sqlbuild.virtual.state.classes.state_backend import StateBackend


class VirtualNodeResultStore(NodeResultStore):
    """State-backed node result store for virtual-mode execution."""

    def __init__(
        self,
        *,
        backend: StateBackend,
        state_connection: Any,
        state_schema: str,
        virtual_environment_name: str,
        target_database: str | None,
        target_schema: str | None,
        target_name: str | None = None,
    ) -> None:
        self.backend: StateBackend = backend
        self.state_connection: Any = state_connection
        self.state_schema: str = state_schema
        self.virtual_environment_name: str = virtual_environment_name
        super().__init__(
            database=target_database,
            schema=target_schema,
            target_name=target_name,
        )

    def write(self, record: NodeResultRecord) -> None:
        scoped_record: NodeResultRecord = NodeResultRecord(
            node_type=record.node_type,
            node_name=record.node_name,
            target_database=self.database,
            target_schema=self.schema,
            target_name=self.target_name,
            run_id=record.run_id,
            status=record.status,
            payload=record.payload,
            metadata=record.metadata,
            error_message=record.error_message,
            materialized=record.materialized,
            ts=record.ts,
        )
        self.backend.insert_node_result(
            connection=self.state_connection,
            schema=self.state_schema,
            virtual_environment_name=self.virtual_environment_name,
            record=scoped_record,
        )
        self._cache_record(record=scoped_record)

    def _read_persisted(self, *, query: NodeResultQuery) -> tuple[NodeResultEnvelope, ...]:
        return self.backend.read_node_results(
            connection=self.state_connection,
            schema=self.state_schema,
            virtual_environment_name=self.virtual_environment_name,
            query=query,
        )
