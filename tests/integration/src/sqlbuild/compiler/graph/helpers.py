"""Helpers for native project graph integration tests."""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

import pytest

import sqlbuild._native as native_module

ORDERS_PROJECT_FILES: dict[str, str] = {
    "sqlbuild_project.toml": 'name = "orders"\nadapter = "duckdb"\n',
    "models/staging/stg_orders.sql": (
        "MODEL (description 'Staged orders.', tags [daily]);\nSELECT 1 AS order_id\n"
    ),
    "models/marts/orders.sql": (
        "MODEL (description 'Orders.');\nSELECT order_id FROM __ref(\"stg_orders\")\n"
    ),
    "models/marts/customers.sql": "MODEL (description 'Customers.');\nSELECT 1 AS customer_id\n",
}
MODEL_NAMES: frozenset[str] = frozenset({"stg_orders", "orders", "customers"})


def write_files(*, project_dir: Path, files: dict[str, str]) -> None:
    """Write project files under `project_dir`."""

    for relative_path, text in files.items():
        path: Path = project_dir / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")


def count_graph_builds(*, monkeypatch: pytest.MonkeyPatch) -> Counter[str]:
    """Count native graphs built from project resources and from Python dict indexes."""

    counts: Counter[str] = Counter()
    graph_type: type[native_module.NativeProjectGraph] = native_module.NativeProjectGraph

    def from_resources(rows: Any) -> native_module.NativeProjectGraph:
        counts["from_resources"] += 1
        return graph_type.from_resources(rows)

    def from_indexes(indexes: Any) -> native_module.NativeProjectGraph:
        counts["from_indexes"] += 1
        return graph_type.from_indexes(indexes)

    counting_type: type = type(
        "NativeProjectGraph",
        (),
        {
            "from_resources": staticmethod(from_resources),
            "from_indexes": staticmethod(from_indexes),
        },
    )
    monkeypatch.setattr(native_module, "NativeProjectGraph", counting_type)
    return counts


def compiled_models(*, stdout: str) -> dict[str, bool]:
    """Whether the compile report lists each project model."""

    return {name: f"── {name} " in stdout for name in sorted(MODEL_NAMES)}
