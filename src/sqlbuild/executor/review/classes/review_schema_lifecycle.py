"""Public review schema lifecycle service."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.adapter.contract.classes.statement_recorder import StatementRecorder
from sqlbuild.errors.contracts.exceptions import ExecutorInputError
from sqlbuild.executor.review._helpers.marker import write_review_marker
from sqlbuild.executor.review.models import ReviewSchemaMarker


class ReviewSchemaLifecycle:
    """Create and drop the run-owned schemas `sqb review` builds into."""

    @staticmethod
    def create(
        *, adapter: BaseAdapter, connection: Any, marker: ReviewSchemaMarker, created_at: datetime
    ) -> None:
        """Mark ownership first, then create the schema, refusing one that already exists."""

        if adapter.schema_exists(
            connection=connection, database=marker.database, schema=marker.schema
        ):
            raise ExecutorInputError(
                f"review schema '{marker.schema}' already exists; another review may be using it",
                code="C765",
            )
        adapter.ensure_schema(
            connection=connection,
            database=marker.marker_database,
            schema=marker.marker_schema,
            statement_recorder=StatementRecorder(),
        )
        write_review_marker(
            adapter=adapter, connection=connection, marker=marker, created_at=created_at
        )
        adapter.ensure_schema(
            connection=connection,
            database=marker.database,
            schema=marker.schema,
            statement_recorder=StatementRecorder(),
        )

    @staticmethod
    def drop(*, adapter: BaseAdapter, connection: Any, database: str | None, schema: str) -> None:
        """Drop the schema and everything in it; the marker stays as ownership evidence."""

        for statement in adapter.render_drop_schema(database=database, schema=schema):
            adapter.execute(connection=connection, sql=statement)

    @staticmethod
    def exists(*, adapter: BaseAdapter, connection: Any, database: str | None, schema: str) -> bool:
        return adapter.schema_exists(connection=connection, database=database, schema=schema)
