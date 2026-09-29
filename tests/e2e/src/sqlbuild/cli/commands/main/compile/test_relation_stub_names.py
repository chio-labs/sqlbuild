"""Authored CTEs named like internal relation stubs must not capture model references."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.compile._test_types import RelationStubNameCase
from tests.e2e.src.sqlbuild.cli.commands.main.compile.helpers import write_relation_stub_project
from tests.e2e.src.sqlbuild.cli.commands.shared.helpers import query_duckdb, run_sqb


@pytest.mark.parametrize(
    "test_case",
    [
        RelationStubNameCase(
            description="lowercase stub-named CTE",
            stub_cte_name="__sqlbuild_project_input_0",
            expected_downstream_type="INTEGER",
            expected_ghost_column_diagnostics=frozenset(
                {("B002", "order_status"), ("B002", "next_order")}
            ),
        ),
        RelationStubNameCase(
            description="uppercase stub-named CTE",
            stub_cte_name="__SQLBUILD_PROJECT_INPUT_0",
            expected_downstream_type="INTEGER",
            expected_ghost_column_diagnostics=frozenset(
                {("B002", "order_status"), ("B002", "next_order")}
            ),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_stub_named_cte_when_compiling_and_building_then_reference_keeps_input_types(
    test_case: RelationStubNameCase,
    tmp_path: Path,
) -> None:
    project: Path = write_relation_stub_project(
        tmp_path=tmp_path, stub_cte_name=test_case.stub_cte_name, selected_column="order_id"
    )

    compiled: subprocess.CompletedProcess[str] = run_sqb(
        project_dir=project, command=("compile", "--no-cache", "--json")
    )

    assert compiled.returncode == 0, compiled.stdout + compiled.stderr
    payload: dict[str, Any] = json.loads(compiled.stdout)
    assert payload["diagnostics"] == []
    built: subprocess.CompletedProcess[str] = run_sqb(project_dir=project, command=("build",))
    assert built.returncode == 0, built.stdout + built.stderr
    assert query_duckdb(
        db_path=project / "orders.duckdb",
        sql=(
            "SELECT column_name, data_type FROM information_schema.columns "
            "WHERE table_name = 'next_order' ORDER BY ordinal_position"
        ),
    ) == [
        ("order_id", test_case.expected_downstream_type),
        ("next_order_id", test_case.expected_downstream_type),
    ]
    assert query_duckdb(
        db_path=project / "orders.duckdb", sql="SELECT order_id, next_order_id FROM next_order"
    ) == [(7, 8)]


@pytest.mark.parametrize(
    "test_case",
    [
        RelationStubNameCase(
            description="lowercase stub-named CTE",
            stub_cte_name="__sqlbuild_project_input_0",
            expected_downstream_type="INTEGER",
            expected_ghost_column_diagnostics=frozenset(
                {("B002", "order_status"), ("B002", "next_order")}
            ),
        ),
        RelationStubNameCase(
            description="uppercase stub-named CTE",
            stub_cte_name="__SQLBUILD_PROJECT_INPUT_0",
            expected_downstream_type="INTEGER",
            expected_ghost_column_diagnostics=frozenset(
                {("B002", "order_status"), ("B002", "next_order")}
            ),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_column_only_in_stub_named_cte_when_compiling_then_reports_unknown_input_column(
    test_case: RelationStubNameCase,
    tmp_path: Path,
) -> None:
    project: Path = write_relation_stub_project(
        tmp_path=tmp_path, stub_cte_name=test_case.stub_cte_name, selected_column="ghost_status"
    )

    compiled: subprocess.CompletedProcess[str] = run_sqb(
        project_dir=project, command=("compile", "--no-cache", "--json")
    )

    assert compiled.returncode == 1, compiled.stdout + compiled.stderr
    payload: dict[str, Any] = json.loads(compiled.stdout)
    assert {
        (diagnostic["code"], diagnostic["resource_name"]) for diagnostic in payload["diagnostics"]
    } == test_case.expected_ghost_column_diagnostics


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
