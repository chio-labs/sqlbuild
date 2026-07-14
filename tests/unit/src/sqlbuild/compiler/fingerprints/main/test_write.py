from __future__ import annotations

import pytest

from sqlbuild.adapters.duckdb.classes.duckdb_adapter import DuckDbAdapter
from sqlbuild.compiler.fingerprints.constants import FINGERPRINT_WRITE_ATTEMPTS
from sqlbuild.compiler.fingerprints.main.write import write_fingerprint
from tests.unit.src.sqlbuild.compiler.fingerprints.main._test_types import (
    WriteFingerprintRetryExhaustionTestCase,
    WriteFingerprintRetryTestCase,
)
from tests.unit.src.sqlbuild.compiler.fingerprints.main.helpers import (
    FlakyFingerprintWriteExecute,
    RecordingSleeper,
    build_write_test_fingerprint,
    render_qualified_name,
)


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
        1
        for sql in execute.executed_sql
        if sql.startswith("INSERT INTO main._sqlbuild_fingerprints")
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
        1
        for sql in execute.executed_sql
        if sql.startswith("INSERT INTO main._sqlbuild_fingerprints")
    )
    assert test_case.expected_error_fragment in str(error_info.value)
    assert execute.create_attempts == test_case.expected_create_attempts
    assert insert_count == test_case.expected_insert_count
