"""Public query-diff artifact lifecycle service."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.executor.diff._helpers.query_artifacts import (
    build_query_diff_artifact,
    cleanup_expired_query_diff_artifacts,
    cleanup_query_diff_artifact,
    inspect_query_diff_artifacts,
    is_query_diff_artifact_name,
    materialize_query_diff_artifact,
)
from sqlbuild.executor.diff.models import (
    QueryDiffArtifact,
    QueryDiffArtifactCleanupResult,
    QueryDiffArtifactInspection,
)


class QueryDiffArtifactLifecycle:
    """Create, inspect, and clean run-owned query-diff artifacts."""

    @staticmethod
    def build(
        *,
        adapter: BaseAdapter,
        run_id: str,
        side: str,
        database: str | None,
        schema: str,
    ) -> QueryDiffArtifact:
        return build_query_diff_artifact(
            adapter=adapter,
            run_id=run_id,
            side=side,
            database=database,
            schema=schema,
        )

    @staticmethod
    def materialize(
        *,
        adapter: BaseAdapter,
        connection: Any,
        artifact: QueryDiffArtifact,
        sql: str,
        expires_at: datetime,
    ) -> None:
        materialize_query_diff_artifact(
            adapter=adapter,
            connection=connection,
            artifact=artifact,
            sql=sql,
            expires_at=expires_at,
        )

    @staticmethod
    def cleanup(*, adapter: BaseAdapter, connection: Any, artifact: QueryDiffArtifact) -> None:
        cleanup_query_diff_artifact(
            adapter=adapter,
            connection=connection,
            artifact=artifact,
        )

    @staticmethod
    def cleanup_expired(
        *,
        adapter: BaseAdapter,
        connection: Any,
        database: str | None,
        schema: str,
        now: datetime,
    ) -> QueryDiffArtifactCleanupResult:
        return cleanup_expired_query_diff_artifacts(
            adapter=adapter,
            connection=connection,
            database=database,
            schema=schema,
            now=now,
        )

    @staticmethod
    def inspect(
        *,
        adapter: BaseAdapter,
        connection: Any,
        database: str | None,
        schema: str,
        now: datetime,
    ) -> QueryDiffArtifactInspection:
        return inspect_query_diff_artifacts(
            adapter=adapter,
            connection=connection,
            database=database,
            schema=schema,
            now=now,
        )

    @staticmethod
    def is_artifact_name(name: str) -> bool:
        return is_query_diff_artifact_name(name)
