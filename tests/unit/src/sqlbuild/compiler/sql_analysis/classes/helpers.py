from __future__ import annotations

import orjson

from sqlbuild.compiler.sql_analysis.classes.binding_catalog import BindingCatalog


def orders_catalog(types: dict[str, str]) -> BindingCatalog:
    """Return a DuckDB catalog whose analysis shape for `orders` has the given types."""

    catalog: BindingCatalog = BindingCatalog(
        dialect="duckdb",
        quoted_ignore_case=False,
        known_functions=(),
        known_types=(),
        relations={},
    )
    retype_orders(catalog=catalog, types=types)
    return catalog


def retype_orders(*, catalog: BindingCatalog, types: dict[str, str]) -> None:
    """Replace the analysis shape for `orders`."""

    catalog.prepare_analysis(
        types={"orders": types}, nullability={"orders": dict.fromkeys(types, "unknown")}
    )


def orders_payload(query_sql: str) -> bytes:
    """Encode one compact analysis batch over the catalog relation `orders`."""

    return orjson.dumps(
        {
            "queries": [
                {
                    "sql": query_sql,
                    "dialect": "duckdb",
                    "analysis_references": [["orders", "orders"]],
                }
            ],
            "templates": [
                {
                    "queryIndex": 0,
                    "recoverCteFacts": True,
                    "references": {"orders": {"resourceType": "model", "resourceName": "orders"}},
                }
            ],
            "projections": [{"templateIndex": 0, "resourceNames": {"orders": "orders"}}],
            "workers": 4,
        }
    )


def analyze_now(*, catalog: BindingCatalog, payload: bytes) -> bytes:
    """Prepare and run one compact batch against the catalog's current shapes."""

    return catalog.native.prepare_compact(payload).run()
