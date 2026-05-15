from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def build_dagster_test_dag() -> Mapping[str, Any]:
    return {
        "version": 1,
        "project_name": "dagster_project",
        "nodes": [
            {
                "id": "source:raw_orders",
                "kind": "source",
                "name": "raw_orders",
                "asset_key": ["raw", "orders"],
                "path": "sources/raw.yml",
            },
            {
                "id": "function:normalize_email",
                "kind": "function",
                "name": "normalize_email",
                "asset_key": ["analytics", "normalize_email"],
                "path": "functions/normalize_email.sql",
                "language": "sql",
            },
            {
                "id": "model:orders",
                "kind": "model",
                "name": "orders",
                "asset_key": ["analytics", "orders"],
                "path": "models/orders.sql",
                "description": "Clean orders",
                "tags": ["daily"],
            },
        ],
        "edges": [
            {"from_id": "source:raw_orders", "to_id": "model:orders"},
            {"from_id": "function:normalize_email", "to_id": "model:orders"},
        ],
        "checks": [
            {
                "id": "audit:not_null:model:orders:order_id",
                "kind": "audit",
                "name": "not_null",
                "checked_asset_ids": ["model:orders"],
                "path": "audits/not_null.sql",
                "attached_column_name": "order_id",
            },
            {
                "id": "audit:freshness:source:raw_orders:loaded_at",
                "kind": "audit",
                "name": "freshness",
                "checked_asset_ids": ["source:raw_orders"],
                "path": "audits/freshness.sql",
                "attached_column_name": "loaded_at",
            },
        ],
    }
