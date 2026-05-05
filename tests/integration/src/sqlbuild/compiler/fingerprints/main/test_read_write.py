from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Any

import pytest

from sqlbuild.adapter.shared.types import FrameworkType
from sqlbuild.compiler.fingerprints.constants import FINGERPRINT_TABLE_NAME
from sqlbuild.compiler.fingerprints.main.read import read_latest_fingerprints
from sqlbuild.compiler.fingerprints.main.write import write_fingerprint
from sqlbuild.compiler.fingerprints.models import Fingerprint, FingerprintSet
from sqlbuild.integrations.duckdb.client import DuckDbAdapter
from tests.integration.src.sqlbuild.compiler.fingerprints.main._test_types import (
    InvalidQuerySqlStorageTestCase,
    LatestResolutionTestCase,
    NullAstHashTestCase,
    ReadNonExistentTableTestCase,
    WriteAndReadTestCase,
    WriteCreatesTableTestCase,
)

RENDER_QUALIFIED_NAME: Callable[..., str | None] = DuckDbAdapter().render_qualified_name
RENDER_FRAMEWORK_TYPE: Callable[[FrameworkType], str] = DuckDbAdapter().render_framework_type

WRITE_AND_READ_TEST_CASES: list[WriteAndReadTestCase] = [
    WriteAndReadTestCase(
        description="writes and reads back a single fingerprint",
        database=None,
        schema="test_schema",
        fingerprints=(
            Fingerprint(
                model_name="orders",
                target_database=None,
                target_schema=None,
                target_name="orders",
                run_id="run_001",
                query_hash="hash_a",
                ast_hash="ast_a",
                schema_fingerprint="schema_a",
                query_sql="SELECT id FROM orders",
                ts=datetime(2026, 1, 15, 12, 0, 0),
            ),
        ),
        expected_model_names=("orders",),
        expected_latest_query_hashes={"orders": "hash_a"},
        expected_latest_target_names={"orders": "orders"},
    ),
    WriteAndReadTestCase(
        description="writes and reads fingerprints for multiple models",
        database=None,
        schema="test_schema",
        fingerprints=(
            Fingerprint(
                model_name="orders",
                target_database=None,
                target_schema=None,
                target_name="orders",
                run_id="run_001",
                query_hash="hash_a",
                ast_hash="ast_a",
                schema_fingerprint="schema_a",
                query_sql="SELECT id FROM orders",
                ts=datetime(2026, 1, 15, 12, 0, 0),
            ),
            Fingerprint(
                model_name="customers",
                target_database=None,
                target_schema=None,
                target_name="customers",
                run_id="run_001",
                query_hash="hash_b",
                ast_hash="ast_b",
                schema_fingerprint="schema_b",
                query_sql="SELECT id FROM customers",
                ts=datetime(2026, 1, 15, 12, 0, 0),
            ),
        ),
        expected_model_names=("customers", "orders"),
        expected_latest_query_hashes={"orders": "hash_a", "customers": "hash_b"},
        expected_latest_target_names={"orders": "orders", "customers": "customers"},
    ),
    WriteAndReadTestCase(
        description="writes and reads multiline query sql with quotes and backslashes",
        database=None,
        schema="test_schema",
        fingerprints=(
            Fingerprint(
                model_name="orders",
                target_database=None,
                target_schema=None,
                target_name="orders",
                run_id="run_001",
                query_hash="hash_a",
                ast_hash="ast_a",
                schema_fingerprint="schema_a",
                query_sql="SELECT '\\n' AS slash_n\nFROM orders\nWHERE note = 'line\\nvalue'",
                ts=datetime(2026, 1, 15, 12, 0, 0),
            ),
        ),
        expected_model_names=("orders",),
        expected_latest_query_hashes={"orders": "hash_a"},
        expected_latest_target_names={"orders": "orders"},
    ),
]


@pytest.mark.parametrize(
    "test_case",
    WRITE_AND_READ_TEST_CASES,
    ids=[case.description for case in WRITE_AND_READ_TEST_CASES],
)
def test_given_fingerprints_when_writing_and_reading_then_returns_expected(
    test_case: WriteAndReadTestCase,
    connection: Any,
    execute: Any,
) -> None:
    fp: Fingerprint
    for fp in test_case.fingerprints:
        write_fingerprint(
            connection=connection,
            execute=execute,
            database=test_case.database,
            schema=test_case.schema,
            fingerprint=fp,
            render_qualified_name=RENDER_QUALIFIED_NAME,
            render_framework_type=RENDER_FRAMEWORK_TYPE,
        )

    result: FingerprintSet = read_latest_fingerprints(
        connection=connection,
        execute=execute,
        database=test_case.database,
        schema=test_case.schema,
        render_qualified_name=RENDER_QUALIFIED_NAME,
    )

    assert tuple(sorted(result.fingerprints.keys())) == test_case.expected_model_names
    model_name: str
    expected_hash: str
    for model_name, expected_hash in test_case.expected_latest_query_hashes.items():
        assert result.fingerprints[model_name].query_hash == expected_hash
    expected_target_name: str | None
    for model_name, expected_target_name in test_case.expected_latest_target_names.items():
        assert result.fingerprints[model_name].target_name == expected_target_name
    fp: Fingerprint
    for fp in test_case.fingerprints:
        assert result.fingerprints[fp.model_name].query_sql == fp.query_sql


@pytest.mark.parametrize(
    "test_case",
    [
        ReadNonExistentTableTestCase(
            description="returns empty set when fingerprint table does not exist",
            database=None,
            schema="test_schema",
            expected_model_count=0,
        ),
    ],
    ids=["returns empty set when fingerprint table does not exist"],
)
def test_given_no_table_when_reading_then_returns_empty_set(
    test_case: ReadNonExistentTableTestCase,
    connection: Any,
    execute: Any,
) -> None:
    result: FingerprintSet = read_latest_fingerprints(
        connection=connection,
        execute=execute,
        database=test_case.database,
        schema=test_case.schema,
        render_qualified_name=RENDER_QUALIFIED_NAME,
    )

    assert len(result.fingerprints) == test_case.expected_model_count


@pytest.mark.parametrize(
    "test_case",
    [
        WriteCreatesTableTestCase(
            description="write creates table if it does not exist",
            database=None,
            schema="test_schema",
            fingerprint=Fingerprint(
                model_name="orders",
                target_database=None,
                target_schema=None,
                target_name="orders",
                run_id="run_001",
                query_hash="hash_a",
                ast_hash="ast_a",
                schema_fingerprint="schema_a",
                query_sql="SELECT 1",
                ts=datetime(2026, 1, 15, 12, 0, 0),
            ),
            expected_table_exists=True,
        ),
    ],
    ids=["write creates table if it does not exist"],
)
def test_given_no_table_when_writing_then_creates_table(
    test_case: WriteCreatesTableTestCase,
    connection: Any,
    execute: Any,
) -> None:
    write_fingerprint(
        connection=connection,
        execute=execute,
        database=test_case.database,
        schema=test_case.schema,
        fingerprint=test_case.fingerprint,
        render_qualified_name=RENDER_QUALIFIED_NAME,
        render_framework_type=RENDER_FRAMEWORK_TYPE,
    )

    row: Any = connection.execute(
        f"SELECT 1 FROM information_schema.tables "
        f"WHERE table_schema = '{test_case.schema}' "
        f"AND table_name = '{FINGERPRINT_TABLE_NAME}'"
    ).fetchone()
    assert (row is not None) == test_case.expected_table_exists


@pytest.mark.parametrize(
    "test_case",
    [
        LatestResolutionTestCase(
            description="resolves latest fingerprint when older row is inserted after newer",
            database=None,
            schema="test_schema",
            fingerprints=(
                Fingerprint(
                    model_name="orders",
                    target_database=None,
                    target_schema=None,
                    target_name="orders",
                    run_id="run_002",
                    query_hash="new_hash",
                    ast_hash="new_ast",
                    schema_fingerprint="new_schema",
                    query_sql="SELECT 2",
                    ts=datetime(2026, 1, 15, 12, 0, 0),
                ),
                Fingerprint(
                    model_name="orders",
                    target_database=None,
                    target_schema=None,
                    target_name="orders",
                    run_id="run_001",
                    query_hash="old_hash",
                    ast_hash="old_ast",
                    schema_fingerprint="old_schema",
                    query_sql="SELECT 1",
                    ts=datetime(2026, 1, 15, 10, 0, 0),
                ),
            ),
            expected_latest_run_id="run_002",
            expected_latest_query_hash="new_hash",
            expected_latest_query_sql="SELECT 2",
        ),
    ],
    ids=["resolves latest fingerprint when older row is inserted after newer"],
)
def test_given_multiple_fingerprints_when_reading_then_resolves_latest(
    test_case: LatestResolutionTestCase,
    connection: Any,
    execute: Any,
) -> None:
    fp: Fingerprint
    for fp in test_case.fingerprints:
        write_fingerprint(
            connection=connection,
            execute=execute,
            database=test_case.database,
            schema=test_case.schema,
            fingerprint=fp,
            render_qualified_name=RENDER_QUALIFIED_NAME,
            render_framework_type=RENDER_FRAMEWORK_TYPE,
        )

    result: FingerprintSet = read_latest_fingerprints(
        connection=connection,
        execute=execute,
        database=test_case.database,
        schema=test_case.schema,
        render_qualified_name=RENDER_QUALIFIED_NAME,
    )
    latest: Fingerprint = result.fingerprints["orders"]

    assert latest.run_id == test_case.expected_latest_run_id
    assert latest.query_hash == test_case.expected_latest_query_hash
    assert latest.query_sql == test_case.expected_latest_query_sql


@pytest.mark.parametrize(
    "test_case",
    [
        NullAstHashTestCase(
            description="preserves null ast hash through write and read",
            database=None,
            schema="test_schema",
            fingerprint=Fingerprint(
                model_name="orders",
                target_database=None,
                target_schema=None,
                target_name="orders",
                run_id="run_001",
                query_hash="hash_a",
                ast_hash=None,
                schema_fingerprint="schema_a",
                query_sql="SELECT 1",
                ts=datetime(2026, 1, 15, 12, 0, 0),
            ),
            expected_ast_hash_is_none=True,
        ),
    ],
    ids=["preserves null ast hash through write and read"],
)
def test_given_null_ast_hash_when_writing_and_reading_then_ast_hash_is_none(
    test_case: NullAstHashTestCase,
    connection: Any,
    execute: Any,
) -> None:
    write_fingerprint(
        connection=connection,
        execute=execute,
        database=test_case.database,
        schema=test_case.schema,
        fingerprint=test_case.fingerprint,
        render_qualified_name=RENDER_QUALIFIED_NAME,
        render_framework_type=RENDER_FRAMEWORK_TYPE,
    )

    result: FingerprintSet = read_latest_fingerprints(
        connection=connection,
        execute=execute,
        database=test_case.database,
        schema=test_case.schema,
        render_qualified_name=RENDER_QUALIFIED_NAME,
    )
    latest: Fingerprint = result.fingerprints["orders"]

    assert (latest.ast_hash is None) == test_case.expected_ast_hash_is_none


@pytest.mark.parametrize(
    "test_case",
    [
        InvalidQuerySqlStorageTestCase(
            description="invalid legacy query sql storage raises contextual error",
            schema="test_schema",
            model_name="orders",
            raw_query_sql_storage="SELECT 1",
            expected_error_fragments=(
                "Invalid fingerprint query SQL storage for 'orders'",
                "expected base64-encoded UTF-8",
                "delete or rebuild",
                "_sqlbuild_fingerprints",
            ),
        )
    ],
    ids=["invalid legacy query sql storage raises contextual error"],
)
def test_given_invalid_query_sql_storage_when_reading_then_raises_contextual_error(
    test_case: InvalidQuerySqlStorageTestCase,
    connection: Any,
    execute: Any,
) -> None:
    connection.execute(f"CREATE SCHEMA IF NOT EXISTS {test_case.schema}")
    connection.execute(
        f"CREATE TABLE {test_case.schema}.{FINGERPRINT_TABLE_NAME} ("
        "model_name VARCHAR NOT NULL, "
        "target_database VARCHAR, "
        "target_schema VARCHAR, "
        "target_name VARCHAR, "
        "run_id VARCHAR NOT NULL, "
        "query_hash VARCHAR NOT NULL, "
        "ast_hash VARCHAR, "
        "schema_fingerprint VARCHAR NOT NULL, "
        "query_sql VARCHAR NOT NULL, "
        "ts TIMESTAMP NOT NULL)"
    )
    connection.execute(
        f"INSERT INTO {test_case.schema}.{FINGERPRINT_TABLE_NAME} VALUES "
        "(?, NULL, ?, ?, ?, ?, NULL, ?, ?, ?)",
        (
            test_case.model_name,
            test_case.schema,
            test_case.model_name,
            "run_001",
            "hash_a",
            "schema_a",
            test_case.raw_query_sql_storage,
            datetime(2026, 1, 15, 12, 0, 0),
        ),
    )

    with pytest.raises(ValueError) as error_info:
        read_latest_fingerprints(
            connection=connection,
            execute=execute,
            database=None,
            schema=test_case.schema,
            render_qualified_name=RENDER_QUALIFIED_NAME,
        )

    message: str = str(error_info.value)
    fragment: str
    for fragment in test_case.expected_error_fragments:
        assert fragment in message
