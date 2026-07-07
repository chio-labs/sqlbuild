from __future__ import annotations

from pathlib import Path

import pytest

from sqlbuild.adapters.duckdb.client import DuckDbAdapter
from tests.integration.src.sqlbuild.compiler.fingerprints.main._test_types import (
    ConcurrentFingerprintWriteTestCase,
)
from tests.integration.src.sqlbuild.compiler.fingerprints.main.helpers import (
    run_concurrent_fingerprint_write_round,
)


@pytest.mark.parametrize(
    "test_case",
    [
        ConcurrentFingerprintWriteTestCase(
            description="eight concurrent writers on a fresh database persist every row",
            writer_count=8,
            round_count=20,
            expected_lost_rows=0,
            expected_failure_count=0,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_fresh_database_when_writers_race_on_state_table_create_then_no_rows_are_lost(
    test_case: ConcurrentFingerprintWriteTestCase,
    adapter: DuckDbAdapter,
    tmp_path: Path,
) -> None:
    failures: list[str] = []
    lost_rows: int = 0
    round_index: int
    for round_index in range(test_case.round_count):
        db_path: Path = tmp_path / f"race_{round_index}.duckdb"
        persisted_count: int = run_concurrent_fingerprint_write_round(
            adapter=adapter,
            db_path=db_path,
            writer_count=test_case.writer_count,
            failures=failures,
        )
        lost_rows += test_case.writer_count - persisted_count

    assert failures == []
    assert lost_rows == test_case.expected_lost_rows
    assert len(failures) == test_case.expected_failure_count
