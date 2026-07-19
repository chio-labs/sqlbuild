"""Shared runtime node-result read and cache behavior."""

from __future__ import annotations

from abc import ABC, abstractmethod

from sqlbuild.errors.contracts.exceptions import ExecutorInputError
from sqlbuild.executor.node_results.models import (
    NodeResultEnvelope,
    NodeResultQuery,
    NodeResultRecord,
)
from sqlbuild.executor.node_results.types import NodeResultStatus
from sqlbuild.executor.python_nodes.constants import MISSING_DEFAULT


class NodeResultStore(ABC):
    """Storage-neutral node-result read and in-run cache contract."""

    def __init__(
        self,
        *,
        database: str | None,
        schema: str | None,
        target_name: str | None = None,
    ) -> None:
        self.database: str | None = database
        self.schema: str | None = schema
        self.target_name: str | None = target_name
        self._cached_results: list[NodeResultEnvelope] = []

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
        cached_results: tuple[NodeResultEnvelope, ...] = self._read_cached_history(
            node_type=node_type,
            node_name=node_name,
            limit=limit,
        )
        if len(cached_results) >= limit:
            return cached_results
        return self._read_persisted(
            query=NodeResultQuery(
                node_type=node_type,
                node_name=node_name,
                target_database=self.database,
                target_schema=self.schema,
                target_name=self.target_name,
                statuses=(NodeResultStatus.SUCCESS.value,),
                run_id=None,
                limit=limit,
            )
        )

    def _read_one(
        self,
        *,
        node_type: str,
        node_name: str,
        run_id: str | None,
    ) -> NodeResultEnvelope | None:
        results: tuple[NodeResultEnvelope, ...] = self._read_persisted(
            query=NodeResultQuery(
                node_type=node_type,
                node_name=node_name,
                target_database=self.database,
                target_schema=self.schema,
                target_name=self.target_name,
                statuses=None if run_id is not None else (NodeResultStatus.SUCCESS.value,),
                run_id=run_id,
                limit=1,
            )
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

    def _cache_record(self, *, record: NodeResultRecord) -> None:
        self._cached_results.insert(
            0,
            NodeResultEnvelope(
                node_type=record.node_type,
                node_name=record.node_name,
                run_id=record.run_id,
                status=record.status,
                payload=record.payload,
                metadata=record.metadata,
                error_message=record.error_message,
                materialized=record.materialized,
                ts=record.ts,
            ),
        )

    @abstractmethod
    def _read_persisted(self, *, query: NodeResultQuery) -> tuple[NodeResultEnvelope, ...]: ...
