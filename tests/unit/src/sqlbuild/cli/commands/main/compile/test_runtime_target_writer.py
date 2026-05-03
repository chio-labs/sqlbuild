from __future__ import annotations

from pathlib import Path

import pytest

from sqlbuild.cli.commands.main.shared.helpers.runtime_target_writer import write_runtime_target
from sqlbuild.compiler.planner.models import PlanOutput
from sqlbuild.executor.build.models import BuildExecutionResult
from tests.unit.src.sqlbuild.cli.commands.main.compile._test_types import TargetWriterTestCase
from tests.unit.src.sqlbuild.cli.commands.main.compile.helpers import (
    build_runtime_target_execution_result,
    build_target_writer_plan_output,
    read_target_files,
)


@pytest.mark.parametrize(
    "test_case",
    [
        TargetWriterTestCase(
            description="writes runtime SQL from executed statements",
            expected_files={
                "run/models/staging/orders.sql": (
                    "DROP TABLE IF EXISTS analytics.orders__staging;\n\n"
                    "CREATE OR REPLACE TABLE analytics.orders__staging AS SELECT 1 AS order_id;\n"
                ),
            },
        )
    ],
    ids=["writes runtime SQL from executed statements"],
)
def test_given_execution_result_when_writing_runtime_target_then_expected_files_are_written(
    test_case: TargetWriterTestCase,
    tmp_path: Path,
) -> None:
    plan_output: PlanOutput = build_target_writer_plan_output()
    result: BuildExecutionResult = build_runtime_target_execution_result()

    write_runtime_target(
        target_dir=tmp_path / "target",
        plan_output=plan_output,
        result=result,
    )

    assert (
        read_target_files(tmp_path / "target", test_case.expected_files) == test_case.expected_files
    )
