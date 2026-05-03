from __future__ import annotations

import json
from pathlib import Path

import pytest

from sqlbuild.cli.commands.main.compile.helpers.compile_target_writer import write_compile_target
from sqlbuild.cli.commands.main.compile.models import WrittenTarget
from sqlbuild.compiler.planner.models import PlanOutput
from tests.unit.src.sqlbuild.cli.commands.main.compile._test_types import TargetWriterTestCase
from tests.unit.src.sqlbuild.cli.commands.main.compile.helpers import (
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
                "compiled/audits/generic/orders/not_null__order_id.sql": (
                    "SELECT order_id FROM analytics.orders WHERE order_id IS NULL\n"
                ),
                "compiled/tests/_chain_/orders__stg_orders/orders_chain.sql": (
                    "SELECT 1 AS order_id\n\nSELECT order_id FROM stg_orders\n"
                ),
            },
            expected_summary_line="Compiled 1 model, 1 seed, 1 audit, 1 test",
        )
    ],
    ids=["writes compiled SQL, manifest, audits, and chain tests"],
)
def test_given_plan_output_when_writing_target_then_expected_files_are_written(
    test_case: TargetWriterTestCase,
    tmp_path: Path,
) -> None:
    plan_output: PlanOutput = build_target_writer_plan_output()
    manifest: dict[str, object] = {"metadata": {"project_name": "demo"}}

    written: WrittenTarget = write_compile_target(
        target_dir=tmp_path / "target",
        plan_output=plan_output,
        manifest=manifest,
    )

    assert written.summary_line() == test_case.expected_summary_line
    assert (
        read_target_files(tmp_path / "target", test_case.expected_files) == test_case.expected_files
    )
    assert json.loads((tmp_path / "target" / "manifest.json").read_text()) == manifest
    assert not (tmp_path / "target" / "run").exists()
