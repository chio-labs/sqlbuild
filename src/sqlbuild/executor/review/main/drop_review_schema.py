"""Drop the run-owned schema one `sqb review` built into."""

from __future__ import annotations

from typing import Any

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.executor.review.classes.review_schema_lifecycle import ReviewSchemaLifecycle


def drop_review_schema(
    *, adapter: BaseAdapter, connection: Any, database: str | None, schema: str
) -> bool:
    """Drop the review schema and everything in it; whether it is gone afterwards."""

    ReviewSchemaLifecycle.drop(
        adapter=adapter, connection=connection, database=database, schema=schema
    )
    return not ReviewSchemaLifecycle.exists(
        adapter=adapter, connection=connection, database=database, schema=schema
    )
