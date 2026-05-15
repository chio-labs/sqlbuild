from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
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
                "id": "seed:waffle_types",
                "kind": "seed",
                "name": "waffle_types",
                "asset_key": ["analytics", "waffle_types"],
                "path": "seeds/waffle_types.csv",
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
                "materialization_type": "table",
            },
            {
                "id": "model:customers",
                "kind": "model",
                "name": "customers",
                "asset_key": ["analytics", "customers"],
                "path": "models/customers.sql",
                "materialization_type": "view",
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
            {
                "id": "sql_scenario:orders_minimal",
                "kind": "scenario",
                "name": "orders_minimal",
                "checked_asset_ids": ["model:orders"],
                "path": "tests/scenarios/orders_minimal.sql",
            },
            {
                "id": "sql_scenario:customers_minimal",
                "kind": "scenario",
                "name": "customers_minimal",
                "checked_asset_ids": ["model:customers"],
                "path": "tests/scenarios/customers_minimal.sql",
            },
        ],
    }


def write_fake_sqb_command(
    *,
    root: Path,
    stdout: str = "",
    stderr: str = "",
    exit_code: int = 0,
    expected_args: tuple[str, ...] | None = None,
) -> list[str]:
    script_path: Path = root / "fake_sqb.py"
    script_path.write_text(
        "\n".join(
            (
                "from __future__ import annotations",
                "from pathlib import Path",
                "import sys",
                f"expected_args = {expected_args!r}",
                "if expected_args is not None and tuple(sys.argv[1:]) != expected_args:",
                "    actual_args = tuple(sys.argv[1:])",
                "    sys.stderr.write(f'expected args {expected_args!r}, got {actual_args!r}\\n')",
                "    raise SystemExit(99)",
                "if len(sys.argv) >= 4 and tuple(sys.argv[1:3]) == ('compile', '--dag'):",
                f"    Path(sys.argv[3]).write_text({stdout!r}, encoding='utf-8')",
                f"sys.stdout.write({stdout!r})",
                f"sys.stderr.write({stderr!r})",
                f"raise SystemExit({exit_code})",
            )
        )
        + "\n",
        encoding="utf-8",
    )
    return ["python", str(script_path)]


def write_dagster_test_dag(*, root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    dag_path: Path = root / "sqlbuild_dag.json"
    dag_path.write_text(json.dumps(build_dagster_test_dag()), encoding="utf-8")
    return dag_path


def assert_select_file_behavior(
    *, command: tuple[str, ...], expected_uses_select_file: bool
) -> None:
    uses_select_file: bool = "--select-file" in command
    assert uses_select_file is expected_uses_select_file
    if uses_select_file:
        select_file_index: int = command.index("--select-file") + 1
        assert not Path(command[select_file_index]).exists()


def assert_positional_selector_behavior(
    *, command: tuple[str, ...], selectors: tuple[str, ...], uses_select_file: bool
) -> None:
    if uses_select_file:
        return
    for selector in selectors:
        assert selector in command
