from __future__ import annotations

from dataclasses import replace
from unittest.mock import Mock

import pytest

from sqlbuild.adapters.duckdb.classes.duckdb_adapter import DuckDbAdapter
from sqlbuild.compiler.fingerprints.constants import FINGERPRINT_WRITE_ATTEMPTS
from sqlbuild.compiler.fingerprints.main.write import write_fingerprint
from sqlbuild.compiler.fingerprints.main.write_many import write_fingerprints
from sqlbuild.compiler.fingerprints.models import Fingerprint
from tests.unit.src.sqlbuild.compiler.fingerprints.main._test_types import (
    WriteFingerprintBatchTestCase,
    WriteFingerprintPartialFailureTestCase,
    WriteFingerprintRetryExhaustionTestCase,
    WriteFingerprintRetryTestCase,
)
from tests.unit.src.sqlbuild.compiler.fingerprints.main.helpers import (
    FakeFingerprintWriteExecute,
    FlakyFingerprintWriteExecute,
    RecordingSleeper,
    build_write_test_fingerprint,
    render_qualified_name,
)


@pytest.mark.parametrize(
    "test_case",
    (
        WriteFingerprintBatchTestCase(
            description="bounds batches by row count",
            fingerprint_count=101,
            definition_size=10,
            expected_rows_per_insert=(50, 50, 1),
            expected_progress=((50, 101), (100, 101), (101, 101)),
        ),
        WriteFingerprintBatchTestCase(
            description="bounds batches by rendered byte size",
            fingerprint_count=2,
            definition_size=300_000,
            expected_rows_per_insert=(1, 1),
            expected_progress=((1, 2), (2, 2)),
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_fingerprints_when_writing_then_creates_once_and_inserts_bounded_batches(
    test_case: WriteFingerprintBatchTestCase,
) -> None:
    execute: FakeFingerprintWriteExecute = FakeFingerprintWriteExecute()
    fingerprints: tuple[Fingerprint, ...] = tuple(
        replace(
            build_write_test_fingerprint(node_name=f"orders_{index}"),
            definition="x" * test_case.definition_size,
        )
        for index in range(test_case.fingerprint_count)
    )
    progress: list[tuple[int, int]] = []

    write_fingerprints(
        connection=object(),
        execute=execute,
        database=None,
        schema="analytics",
        fingerprints=fingerprints,
        render_qualified_name=render_qualified_name,
        render_framework_type=DuckDbAdapter().render_framework_type,
        on_progress=lambda completed, total: progress.append((completed, total)),
    )

    insert_statements: tuple[str, ...] = tuple(execute.executed_sql[1:])
    assert execute.executed_sql[0].startswith("CREATE TABLE")
    assert tuple(sql.count("), (") + 1 for sql in insert_statements) == (
        test_case.expected_rows_per_insert
    )
    assert tuple(progress) == test_case.expected_progress


@pytest.mark.parametrize(
    "test_case",
    (
        WriteFingerprintPartialFailureTestCase(
            description="only confirms rows from completed batches",
            fingerprint_count=51,
            expected_execute_count=7,
            expected_progress=((50, 51),),
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_later_batch_failure_when_writing_then_progress_only_confirms_completed_rows(
    test_case: WriteFingerprintPartialFailureTestCase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    execute: Mock = Mock(
        side_effect=(None, None, *([RuntimeError("warehouse request interrupted")] * 5))
    )
    monkeypatch.setattr(
        "sqlbuild.compiler.fingerprints._helpers.write_many.time.sleep", lambda _: None
    )
    progress: list[tuple[int, int]] = []

    with pytest.raises(RuntimeError, match="warehouse request interrupted"):
        write_fingerprints(
            connection=object(),
            execute=execute,
            database=None,
            schema="analytics",
            fingerprints=tuple(
                build_write_test_fingerprint(node_name=f"orders_{index}")
                for index in range(test_case.fingerprint_count)
            ),
            render_qualified_name=render_qualified_name,
            render_framework_type=DuckDbAdapter().render_framework_type,
            on_progress=lambda completed, total: progress.append((completed, total)),
        )

    assert execute.call_count == test_case.expected_execute_count
    assert execute.call_args_list[0].kwargs["sql"].startswith("CREATE TABLE")
    assert execute.call_args_list[1].kwargs["sql"].startswith("INSERT INTO")
    assert tuple(progress) == test_case.expected_progress


@pytest.mark.parametrize(
    "test_case",
    [
        WriteFingerprintRetryTestCase(
            description="retries once past a concurrent create conflict and inserts the row",
            failing_create_attempts=1,
            error_message='Catalog write-write conflict on create with "_sqlbuild_fingerprints"',
            expected_create_attempts=2,
            expected_insert_count=1,
            expected_sleep_count=1,
        ),
        WriteFingerprintRetryTestCase(
            description="retries through repeated conflicts up to the attempt budget",
            failing_create_attempts=FINGERPRINT_WRITE_ATTEMPTS - 1,
            error_message='Catalog write-write conflict on create with "_sqlbuild_fingerprints"',
            expected_create_attempts=FINGERPRINT_WRITE_ATTEMPTS,
            expected_insert_count=1,
            expected_sleep_count=FINGERPRINT_WRITE_ATTEMPTS - 1,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_transient_write_conflicts_when_writing_fingerprint_then_retries_until_insert(
    test_case: WriteFingerprintRetryTestCase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter: DuckDbAdapter = DuckDbAdapter()
    execute: FlakyFingerprintWriteExecute = FlakyFingerprintWriteExecute(
        failing_create_attempts=test_case.failing_create_attempts,
        error_message=test_case.error_message,
    )
    sleeper: RecordingSleeper = RecordingSleeper()
    monkeypatch.setattr("sqlbuild.compiler.fingerprints.main.write.time.sleep", sleeper)

    write_fingerprint(
        connection=object(),
        execute=execute,
        database=None,
        schema="main",
        fingerprint=build_write_test_fingerprint(),
        render_qualified_name=render_qualified_name,
        render_framework_type=adapter.render_framework_type,
    )

    insert_count: int = sum(
        sql.startswith("INSERT INTO main._sqlbuild_fingerprints") for sql in execute.executed_sql
    )
    assert execute.create_attempts == test_case.expected_create_attempts
    assert insert_count == test_case.expected_insert_count
    assert len(sleeper.sleep_seconds) == test_case.expected_sleep_count
    assert sleeper.sleep_seconds == sorted(sleeper.sleep_seconds)


@pytest.mark.parametrize(
    "test_case",
    [
        WriteFingerprintRetryExhaustionTestCase(
            description="raises the final error once the retry budget is exhausted",
            error_message='Catalog write-write conflict on create with "_sqlbuild_fingerprints"',
            expected_create_attempts=FINGERPRINT_WRITE_ATTEMPTS,
            expected_insert_count=0,
            expected_error_fragment="Catalog write-write conflict",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_persistent_write_conflicts_when_writing_fingerprint_then_raises_after_budget(
    test_case: WriteFingerprintRetryExhaustionTestCase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter: DuckDbAdapter = DuckDbAdapter()
    execute: FlakyFingerprintWriteExecute = FlakyFingerprintWriteExecute(
        failing_create_attempts=FINGERPRINT_WRITE_ATTEMPTS,
        error_message=test_case.error_message,
    )
    sleeper: RecordingSleeper = RecordingSleeper()
    monkeypatch.setattr("sqlbuild.compiler.fingerprints.main.write.time.sleep", sleeper)

    with pytest.raises(RuntimeError) as error_info:
        write_fingerprint(
            connection=object(),
            execute=execute,
            database=None,
            schema="main",
            fingerprint=build_write_test_fingerprint(),
            render_qualified_name=render_qualified_name,
            render_framework_type=adapter.render_framework_type,
        )

    insert_count: int = sum(
        sql.startswith("INSERT INTO main._sqlbuild_fingerprints") for sql in execute.executed_sql
    )
    assert test_case.expected_error_fragment in str(error_info.value)
    assert execute.create_attempts == test_case.expected_create_attempts
    assert insert_count == test_case.expected_insert_count
