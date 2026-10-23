"""Create the run-owned schema one `sqb review` builds into."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.executor.review.classes.review_schema_lifecycle import ReviewSchemaLifecycle
from sqlbuild.executor.review.models import ReviewSchemaMarker


def create_review_schema(
    *,
    adapter: BaseAdapter,
    connection: Any,
    database: str | None,
    schema: str,
    marker_database: str | None,
    marker_schema: str,
    run_id: str,
    created_at: datetime,
) -> None:
    """Record ownership in the marker schema, then create the review schema."""

    ReviewSchemaLifecycle.create(
        adapter=adapter,
        connection=connection,
        marker=ReviewSchemaMarker(
            database=database,
            schema=schema,
            marker_database=marker_database,
            marker_schema=marker_schema,
            run_id=run_id,
        ),
        created_at=created_at,
    )
