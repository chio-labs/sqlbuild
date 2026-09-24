"""Fingerprint builders for migration fingerprint unit tests."""

from __future__ import annotations

import json

from sqlbuild.compiler.planner._helpers.migrations.fingerprint import build_migration_fingerprint

BASE_CONFIG: dict[str, object] = {
    "materialized": "incremental",
    "incremental_strategy": "delete_insert",
    "unique_key": "order_id",
    "cursor": "order_date",
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
