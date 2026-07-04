"""Seed executor tests."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from sqlbuild.adapter.shared.models import StatementRecorder
from sqlbuild.adapters.duckdb.client import DuckDbAdapter
from sqlbuild.compiler.fingerprints.constants import FINGERPRINT_TABLE_NAME
from sqlbuild.executor.build.models import SeedExecutionResult
from sqlbuild.executor.seed.main.execute import execute_seed
from sqlbuild.executor.shared.types import ExecutionStatus
from tests.unit.src.sqlbuild.executor.seed.main._test_types import (
    SeedFingerprintFailureTestCase,
)
from tests.unit.src.sqlbuild.executor.seed.main.helpers import build_seed_plan_entry


@pytest.mark.parametrize(
    "test_case",
    [
        SeedFingerprintFailureTestCase(
            description="failed seed load does not write fingerprint state",
            seed_name="missing_seed",
            missing_file_path=Path("missing.csv"),
            expected_status=ExecutionStatus.FAILED,
            expected_fingerprint_table_exists=False,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_seed_load_failure_when_executing_then_does_not_write_fingerprint(
    test_case: SeedFingerprintFailureTestCase,
    tmp_path: Path,
) -> None:
    adapter: DuckDbAdapter = DuckDbAdapter()
    connection: Any = adapter.connect({"database": ":memory:"})

    result: SeedExecutionResult = execute_seed(
        seed_entry=build_seed_plan_entry(
            seed_name=test_case.seed_name,
            file_path=tmp_path / test_case.missing_file_path,
        ),
        adapter=adapter,
        connection=connection,
        statement_recorder=StatementRecorder(),
        run_id="seed-failure-test",
        query_change_tracking=True,
    )

    assert result.status == test_case.expected_status
    assert (
        adapter.relation_exists(
            connection,
            database=None,
            schema="main",
            name=FINGERPRINT_TABLE_NAME,
        )
        is test_case.expected_fingerprint_table_exists
    )
