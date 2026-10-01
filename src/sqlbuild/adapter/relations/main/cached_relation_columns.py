"""Read one relation's columns through the open relation metadata cache."""

from __future__ import annotations

from functools import partial
from typing import Any

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.adapter.contract.models import ColumnInfo
from sqlbuild.adapter.relations._helpers.relation_metadata_context import (
    read_through_relation_metadata_cache,
)
from sqlbuild.adapter.relations.constants import RELATION_COLUMNS_LOOKUP


def cached_relation_columns(
    *, adapter: BaseAdapter, connection: Any, database: str | None, schema: str | None, name: str
) -> tuple[ColumnInfo, ...]:
    """Return ``adapter.get_columns`` for this lookup, reusing a cached identical read."""

    return read_through_relation_metadata_cache(
        adapter=adapter,
        kind=RELATION_COLUMNS_LOOKUP,
        database=database,
        schema=schema,
        name=name,
        read=partial(
            adapter.get_columns, connection=connection, database=database, schema=schema, name=name
        ),
    )
