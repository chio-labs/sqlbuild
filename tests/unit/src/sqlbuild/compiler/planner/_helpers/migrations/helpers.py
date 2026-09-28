"""Fingerprint builders for migration fingerprint unit tests."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from sqlbuild.compiler.compile.models import CompiledRelationLocation
from sqlbuild.compiler.migrations.types import OldNameViewAction
from sqlbuild.compiler.planner._helpers.migrations.fingerprint import build_migration_fingerprint
from sqlbuild.compiler.planner._helpers.migrations.projections import parse_query_shape
from sqlbuild.compiler.planner.models import OldNameViewPlanEntry, QueryShape
from sqlbuild.compiler.planner.types import InputColumns

BASE_CONFIG: dict[str, object] = {
    "materialized": "incremental",
    "incremental_strategy": "delete_insert",
    "unique_key": "order_id",
    "cursor": "order_date",
}
ORDERS_INPUTS: dict[tuple[str, str], frozenset[str]] = {
    ("__source", "raw_orders"): frozenset({"order_id", "order_date", "amount", "tax"})
}
ORDERS_SQL: str = 'SELECT o.order_id, o.amount_cents FROM __ref("stg_orders") AS o'


def model_fingerprint(
    *, model_name: str, query_sql: str, config: dict[str, object], ref_identities: dict[str, str]
) -> str | None:
    """Return the DuckDB migration fingerprint for one model definition."""

    return build_migration_fingerprint(
        query_sql=query_sql,
        metadata_json=json.dumps({"model_name": model_name, "config": config}),
        ref_identities=ref_identities,
        dialect="duckdb",
    )


def query_shape(query_sql: str) -> QueryShape:
    """Return the DuckDB query shape of one readable model query."""

    shape: QueryShape | None = parse_query_shape(query_sql=query_sql, dialect="duckdb")
    assert shape is not None, query_sql
    return shape


def input_lookup(relations: dict[tuple[str, str], frozenset[str]]) -> InputColumns:
    """Return an input-column lookup over (reference kind, relation name) pairs."""

    return lambda kind, name: relations.get((kind, name))


def old_name_entry(
    *,
    action: str,
    column_aliases: tuple[tuple[str, str], ...],
    grants_supported: bool,
    grants_copied: int | None,
    reason: str | None,
) -> OldNameViewPlanEntry:
    """Return an old-name plan entry for prod.revenue expiring on 2026-10-28."""

    return OldNameViewPlanEntry(
        model_name="daily_revenue",
        origin=CompiledRelationLocation(
            database=None, schema="prod", name="revenue", qualified_name="prod.revenue"
        ),
        destination=CompiledRelationLocation(
            database=None, schema="prod", name="daily_revenue", qualified_name="prod.daily_revenue"
        ),
        action=OldNameViewAction(action),
        target_name="prod",
        retention="30d",
        expires_at=datetime(2026, 10, 28, tzinfo=UTC),
        column_aliases=column_aliases,
        reason=reason,
        grants_copied=grants_copied,
        grants_supported=grants_supported,
    )
