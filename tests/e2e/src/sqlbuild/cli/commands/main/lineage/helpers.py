from __future__ import annotations

from pathlib import Path
from typing import cast

from tests.e2e.src.sqlbuild.cli.commands.shared.helpers import prepare_inline_project


def prepare_lineage_cache_project(*, tmp_path: Path) -> Path:
    return prepare_inline_project(
        tmp_path=tmp_path,
        project_name="lineage_cache_project",
        repo_files={
            "sqlbuild_project.toml": 'name = "lineage_cache_project"\nadapter = "duckdb"\n',
            "models/stg_orders.sql": (
                "MODEL (materialized view);\n\nSELECT 1 AS order_id, 10 AS customer_id\n"
            ),
            "models/stg_customers.sql": (
                "MODEL (materialized view);\n\nSELECT 10 AS customer_id\n"
            ),
            "models/fact_orders.sql": (
                'MODEL (materialized view);\n\nSELECT * FROM __ref("stg_orders")\n'
            ),
        },
    )


def lineage_node_ids(*, payload: dict[str, object]) -> tuple[str, ...]:
    nodes: list[dict[str, object]] = cast(list[dict[str, object]], payload["nodes"])
    return tuple(str(node["id"]) for node in nodes)
