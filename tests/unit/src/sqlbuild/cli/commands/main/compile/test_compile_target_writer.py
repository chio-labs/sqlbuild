from __future__ import annotations

import json
from pathlib import Path

import pytest

from sqlbuild.adapters.duckdb.client import DuckDbAdapter
from sqlbuild.cli.commands.helpers.compile.models import WrittenTarget
from sqlbuild.cli.commands.helpers.compile.target_writer import (
    write_compile_target,
    write_static_compile_target,
)
from sqlbuild.compiler.compile.models.core import CompiledProject
from sqlbuild.compiler.planner.models import PlanOutput
from sqlbuild.executor.testing.main.comparison_sql import build_sql_test_comparison_sql
from tests.unit.src.sqlbuild.cli.commands.main.compile._test_types import (
    TargetWriterTestCase,
)
from tests.unit.src.sqlbuild.cli.commands.main.compile.helpers import (
    build_static_target_writer_project,
    build_target_writer_plan_output,
    read_target_files,
)


@pytest.mark.parametrize(
    "test_case",
    [
        TargetWriterTestCase(
            description="writes compiled SQL, manifest, audits, and chain tests",
            expected_files={
                "compiled/models/staging/orders.sql": "SELECT 1 AS order_id\n",
                "compiled/functions/sql/is_completed_order.sql": (
                    "CREATE OR REPLACE MACRO analytics.is_completed_order(order_status) AS (\n"
                    "order_status = 'completed'\n"
                    ")\n"
                ),
                "compiled/functions/python/is_completed_order_py.sql": (
                    "REGISTER PYTHON FUNCTION analytics.is_completed_order_py"
                    "(VARCHAR) RETURNS BOOLEAN\n"
                ),
                "compiled/audits/generic/orders/not_null__order_id.sql": (
                    "SELECT order_id FROM analytics.orders WHERE order_id IS NULL\n"
                ),
            },
            expected_summary_line="Compiled 1 model, 1 seed, 2 functions, 1 audit, 1 test",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_plan_output_when_writing_target_then_expected_files_are_written(
    test_case: TargetWriterTestCase,
    tmp_path: Path,
) -> None:
    plan_output: PlanOutput = build_target_writer_plan_output()
    expected_test_sql: str = (
        build_sql_test_comparison_sql(test_entry=plan_output.test_entries[0]) + "\n"
    )
    manifest: dict[str, object] = {"metadata": {"project_name": "demo"}}

    expected_files: dict[str, str] = dict(test_case.expected_files)
    expected_files["compiled/tests/_chain_/orders__stg_orders/orders_chain.sql"] = expected_test_sql

    written: WrittenTarget = write_compile_target(
        target_dir=tmp_path / "target",
        adapter=DuckDbAdapter(),
        plan_output=plan_output,
        manifest=manifest,
    )

    assert written.summary_line() == test_case.expected_summary_line
    assert read_target_files(tmp_path / "target", expected_files) == expected_files
    assert json.loads((tmp_path / "target" / "manifest.json").read_text()) == manifest
    assert not (tmp_path / "target" / "run").exists()


@pytest.mark.parametrize(
    "test_case",
    [
        TargetWriterTestCase(
            description="writes offline compiled SQL without manifest by default",
            expected_files={
                "compiled/models/staging/orders.sql": "SELECT 2 AS order_id\n",
                "compiled/functions/sql/is_completed_order.sql": (
                    "CREATE OR REPLACE MACRO analytics.is_completed_order(order_status) AS (\n"
                    "order_status = 'completed'\n"
                    ")\n"
                ),
            },
            expected_summary_line="Compiled 1 model, 1 function",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_compiled_project_when_writing_static_target_then_expected_files_are_written(
    test_case: TargetWriterTestCase,
    tmp_path: Path,
) -> None:
    project: CompiledProject = build_static_target_writer_project()

    written: WrittenTarget = write_static_compile_target(
        target_dir=tmp_path / "target",
        adapter=DuckDbAdapter(),
        project=project,
    )

    assert written.summary_line() == test_case.expected_summary_line
    assert (
        read_target_files(tmp_path / "target", test_case.expected_files) == test_case.expected_files
    )
    assert not (tmp_path / "target" / "manifest.json").exists()
