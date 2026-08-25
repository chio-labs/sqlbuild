"""Default adapter implementations for native microbatch contracts."""

from __future__ import annotations

from typing import Any, cast

from sqlbuild.adapter.contract.models import RelationInfo


class MicrobatchMixin:
    """Provide conservative portable defaults for first-class warehouse adapters."""

    def supports_concurrent_microbatch_dml(self) -> bool:
        """Return whether disjoint same-target delete/insert batches may run concurrently."""

        return False

    def physical_relation_generation(
        self,
        *,
        connection: Any,
        database: str | None,
        schema: str | None,
        name: str,
    ) -> str | None:
        """Return the relation creation timestamp when the adapter exposes one."""

        adapter: Any = cast(Any, self)
        relations: tuple[RelationInfo, ...] = adapter.list_relations(
            connection=connection,
            database=database,
            schemas=None if schema is None else (schema,),
            names=(name,),
        )
        if len(relations) != 1 or relations[0].created_at is None:
            return None
        return relations[0].created_at.isoformat()

    def render_create_microbatch_state_table_sql(self, *, database: str | None, schema: str) -> str:
        """Render portable DDL for the direct microbatch state table."""

        from sqlbuild.microbatches.main.create_table_sql import build_create_table_sql

        adapter: Any = cast(Any, self)
        return build_create_table_sql(
            database=database,
            schema=schema,
            render_qualified_name=adapter.render_qualified_name,
            render_framework_type=adapter.render_framework_type,
        )

    def render_create_microbatch_state_index_sqls(
        self, *, database: str | None, schema: str
    ) -> tuple[str, ...]:
        """Return no index DDL unless the warehouse adapter explicitly opts in."""

        return ()
