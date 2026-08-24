from __future__ import annotations

import json
import os
from dataclasses import replace
from pathlib import Path

import pytest

from sqlbuild.adapters.duckdb.classes.duckdb_adapter import DuckDbAdapter
from sqlbuild.cli.commands._helpers.compile.target_writer import (
    write_compile_target,
    write_static_compile_target,
)
from sqlbuild.cli.commands.models import WrittenTarget
from sqlbuild.compiler.compile.models import CompiledProject
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
    manifest_path: Path = tmp_path / "target" / "manifest.json"
    unchanged_mtime_ns: int = 1_000_000_000
    os.utime(manifest_path, ns=(unchanged_mtime_ns, unchanged_mtime_ns))
    _ = write_compile_target(
        target_dir=tmp_path / "target",
        adapter=DuckDbAdapter(),
        plan_output=plan_output,
        manifest=manifest,
    )

    assert written.summary_line() == test_case.expected_summary_line
    assert read_target_files(tmp_path / "target", expected_files) == expected_files
    assert json.loads(manifest_path.read_text()) == manifest
    assert manifest_path.stat().st_mtime_ns == unchanged_mtime_ns
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
    target_dir: Path = tmp_path / "target"
    stale_path: Path = target_dir / "compiled" / "models" / "deleted.sql"
    stale_path.parent.mkdir(parents=True)
    stale_path.write_text("SELECT 'stale'\n", encoding="utf-8")

    written: WrittenTarget = write_static_compile_target(
        target_dir=target_dir,
        adapter=DuckDbAdapter(),
        project=project,
    )
    model_path: Path = target_dir / "compiled" / "models" / "staging" / "orders.sql"
    unchanged_mtime_ns: int = 1_000_000_000
    os.utime(model_path, ns=(unchanged_mtime_ns, unchanged_mtime_ns))
    _ = write_static_compile_target(
        target_dir=target_dir,
        adapter=DuckDbAdapter(),
        project=project,
    )

    assert written.summary_line() == test_case.expected_summary_line
    assert read_target_files(target_dir, test_case.expected_files) == test_case.expected_files
    assert model_path.stat().st_mtime_ns == unchanged_mtime_ns
    assert not stale_path.exists()
    assert not (target_dir / "manifest.json").exists()

    changed_project: CompiledProject = replace(
        project,
        models=(replace(project.models[0], query_sql="SELECT 3 AS order_id"),),
    )
    _ = write_static_compile_target(
        target_dir=target_dir,
        adapter=DuckDbAdapter(),
        project=changed_project,
    )

    assert model_path.read_text(encoding="utf-8") == "SELECT 3 AS order_id\n"
    assert model_path.stat().st_mtime_ns != unchanged_mtime_ns
