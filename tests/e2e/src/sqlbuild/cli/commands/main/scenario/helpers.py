"""Helpers for sqb scenario command e2e tests."""

from __future__ import annotations

import json
from pathlib import Path

from tests.e2e.src.sqlbuild.cli.commands.main.shared.helpers import query_duckdb


def build_scenario_project_files() -> dict[str, str]:
    """Build an inline project with passing and failing SQL scenarios."""

    return {
        "sqlbuild_project.toml": (
            'name = "scenario_demo"\n'
            'adapter = "duckdb"\n\n'
            "[connection]\n"
            'database = "scenario_demo.duckdb"\n\n'
            "[defaults]\n"
            'materialized = "table"\n'
        ),
        "sources/raw.yml": (
            "sources:\n  - name: raw_orders\n    schema: main\n    table: raw_orders\n"
        ),
        "models/orders.sql": (
            "MODEL (materialized table);\n\n"
            "SELECT\n"
            "  id AS order_id,\n"
            "  amount\n"
            'FROM __source("raw_orders")\n'
        ),
        "models/order_totals.sql": (
            "MODEL (materialized table);\n\n"
            "SELECT\n"
            "  SUM(amount) AS total_amount\n"
            'FROM __ref("orders")\n'
        ),
        "tests/scenarios/order_totals_pass.sql": (
            'SCENARIO (description: "Order totals scenario", tags: ["scenario"]);\n\n'
            "WITH\n"
            "__source__raw_orders AS (\n"
            "  SELECT 1 AS id, 10 AS amount\n"
            "  UNION ALL\n"
            "  SELECT 2 AS id, 5 AS amount\n"
            "),\n"
            "__expected__order_totals AS (\n"
            "  SELECT 15 AS total_amount\n"
            ")\n"
            "SELECT 1\n"
        ),
        "tests/scenarios/nested/orders_assert_pass.sql": (
            "SCENARIO ();\n\n"
            "WITH\n"
            "__source__raw_orders AS (\n"
            "  SELECT 1 AS id, 10 AS amount\n"
            "),\n"
            "__assert__no_negative_orders AS (\n"
            '  SELECT * FROM __ref("orders") WHERE amount < 0\n'
            ")\n"
            "SELECT 1\n"
        ),
        "tests/scenarios/order_totals_fail.sql": (
            "SCENARIO ();\n\n"
            "WITH\n"
            "__source__raw_orders AS (\n"
            "  SELECT 1 AS id, 10 AS amount\n"
            "),\n"
            "__expected__order_totals AS (\n"
            "  SELECT 11 AS total_amount\n"
            ")\n"
            "SELECT 1\n"
        ),
    }


def list_scenario_relation_names(*, db_path: Path) -> tuple[str, ...]:
    """Return DuckDB relation names owned by scenario artifact prefixes."""

    rows: list[tuple[object, ...]] = query_duckdb(
        db_path=db_path,
        sql=(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'main' AND table_name LIKE '__sqb_%' "
            "ORDER BY table_name"
        ),
    )
    return tuple(str(row[0]) for row in rows)


def scenario_relation_name_by_suffix(*, db_path: Path, suffix: str) -> str:
    """Return one retained scenario relation name ending with the requested suffix."""

    matches: tuple[str, ...] = tuple(
        relation_name
        for relation_name in list_scenario_relation_names(db_path=db_path)
        if relation_name.endswith(suffix)
    )
    assert len(matches) == 1
    return matches[0]


def scenario_relation_row_count(*, db_path: Path, relation_name: str) -> int:
    """Return row count for one retained scenario relation."""

    rows: list[tuple[object, ...]] = query_duckdb(
        db_path=db_path,
        sql=f'SELECT COUNT(*) FROM main."{relation_name}"',
    )
    return int(rows[0][0])


def assert_runtime_artifact_contains(
    *, project_dir: Path, relative_path: Path, expected_fragments: tuple[str, ...]
) -> None:
    """Assert a scenario runtime artifact exists and contains expected fragments."""

    artifact_path: Path = project_dir / relative_path
    assert artifact_path.exists(), f"missing runtime artifact: {artifact_path}"
    content: str = artifact_path.read_text(encoding="utf-8")
    expected_fragment: str
    for expected_fragment in expected_fragments:
        assert expected_fragment in content


def assert_scenario_snapshot(
    *, project_dir: Path, scenario_name: str, expected_row_count: int
) -> None:
    """Assert a scenario snapshot manifest and source JSONL file were written."""

    snapshot_root: Path = project_dir / "tests" / "_scenario_snapshots" / scenario_name
    manifest_path: Path = snapshot_root / "scenario.json"
    jsonl_path: Path = snapshot_root / "sources" / "raw_orders.jsonl"
    assert manifest_path.exists()
    assert jsonl_path.exists()

    manifest_data: object = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert isinstance(manifest_data, dict)
    assert manifest_data["scenario_name"] == scenario_name
    assert manifest_data["format"] == "jsonl"
    assert manifest_data["total_rows"] == expected_row_count
    assert manifest_data["relations"][0]["file"] == "sources/raw_orders.jsonl"
    assert manifest_data["relations"][0]["row_count"] == expected_row_count

    rows: list[str] = jsonl_path.read_text(encoding="utf-8").splitlines()
    assert len(rows) == expected_row_count
