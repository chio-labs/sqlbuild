"""Check one relation's existence through the open relation metadata cache."""

from __future__ import annotations

from functools import partial
from typing import Any

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.adapter.relations._helpers.relation_metadata_context import (
    read_through_relation_metadata_cache,
)
from sqlbuild.adapter.relations.constants import RELATION_EXISTS_LOOKUP


def cached_relation_exists(
    *, adapter: BaseAdapter, connection: Any, database: str | None, schema: str | None, name: str
) -> bool:
    """Return ``adapter.relation_exists`` for this lookup, reusing a cached identical read."""

    return read_through_relation_metadata_cache(
        adapter=adapter,
        kind=RELATION_EXISTS_LOOKUP,
        database=database,
        schema=schema,
        name=name,
        read=partial(
            adapter.relation_exists,
            connection=connection,
            database=database,
            schema=schema,
            name=name,
        ),
    )
