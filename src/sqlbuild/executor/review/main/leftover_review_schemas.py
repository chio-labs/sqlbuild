"""Find review schemas an earlier run created and did not drop."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.executor.review._helpers.marker import marked_review_schemas
from sqlbuild.executor.review.models import LeftoverReviewSchema


def leftover_review_schemas(
    *,
    adapter: BaseAdapter,
    connection: Any,
    database: str | None,
    schema: str,
    now: datetime,
    max_age: timedelta,
) -> tuple[LeftoverReviewSchema, ...]:
    """Marked review schemas older than `max_age` that still exist."""

    return tuple(
        leftover
        for leftover in marked_review_schemas(
            adapter=adapter, connection=connection, database=database, schema=schema
        )
        if now - leftover.created_at >= max_age
        and adapter.schema_exists(
            connection=connection, database=leftover.database, schema=leftover.schema
        )
    )
