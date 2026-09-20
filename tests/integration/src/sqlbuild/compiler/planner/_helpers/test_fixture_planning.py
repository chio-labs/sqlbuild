from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from sqlbuild.adapters.duckdb.classes.duckdb_adapter import DuckDbAdapter
from sqlbuild.compiler.compile.models import CompiledProject
from sqlbuild.compiler.discovery.main.discover import discover_project_inputs
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.compiler.pipeline.main.project import compile_project
from sqlbuild.compiler.planner._helpers.output.plan_output import build_selected_test_entries
from sqlbuild.compiler.planner.models import SqlTestPlanEntry
from tests.integration.src.sqlbuild.compiler.planner._helpers._test_types import (
    FixturePlanningIntegrationTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    (
        FixturePlanningIntegrationTestCase(
            description="partial source fixture",
            expected_sql_fragment='CAST(NULL AS VARCHAR) AS "status"',
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_partial_fixture_when_compiling_and_planning_then_completes_required_columns(
    test_case: FixturePlanningIntegrationTestCase,
    tmp_path: Path,
    write_repo_files: Callable[[Path, dict[str, str]], None],
) -> None:
    write_repo_files(
        tmp_path,
        {
            "sqlbuild_project.toml": (
                'name = "fixture_cache_demo"\n'
                'adapter = "duckdb"\n\n'
                "[connection]\n"
                'database = ":memory:"\n'
            ),
            "models/orders.sql": (
                'MODEL ();\n\nSELECT order_id, status FROM __source("raw_orders")\n'
            ),
            "sources/raw_orders.yml": (
                "sources:\n"
                "  - name: raw_orders\n"
                "    expression: SELECT 1 AS order_id, 'open' AS status\n"
                "    columns:\n"
                "      - name: order_id\n        type: INTEGER\n        nullable: false\n"
                "      - name: status\n        type: VARCHAR\n        nullable: true\n"
            ),
            "tests/unit/test_orders.sql": (
                "TEST();\n\n"
                "WITH\n"
                "__source__raw_orders AS (SELECT 1 AS order_id),\n"
                "__expected__orders AS (\n"
                "  SELECT 1 AS order_id, CAST(NULL AS VARCHAR) AS status\n"
                ")\n"
                "SELECT 1\n"
            ),
        },
    )
    discovered_inputs: DiscoveredProjectInputs = discover_project_inputs(project_dir=tmp_path)
    adapter: DuckDbAdapter = DuckDbAdapter()

    project: CompiledProject = compile_project(
        discovered_inputs=discovered_inputs,
        adapter=adapter,
    )
    entries, warnings = build_selected_test_entries(
        project=project,
        adapter=adapter,
        selected_keys=frozenset((project.models[0].key,)),
    )

    assert warnings == []
    assert len(entries) == 1
    entry: SqlTestPlanEntry = entries[0]
    assert test_case.expected_sql_fragment in entry.chain[0].resolved_sql


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
