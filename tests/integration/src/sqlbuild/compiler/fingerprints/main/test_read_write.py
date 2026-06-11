from __future__ import annotations

import json
from collections.abc import Callable
from datetime import datetime
from typing import Any

import pytest

from sqlbuild.adapter.shared.types import FrameworkType
from sqlbuild.adapters.duckdb.client import DuckDbAdapter
from sqlbuild.compiler.fingerprints.constants import FINGERPRINT_TABLE_NAME
from sqlbuild.compiler.fingerprints.main.read import read_latest_fingerprints
from sqlbuild.compiler.fingerprints.main.write import write_fingerprint
from sqlbuild.compiler.fingerprints.models import Fingerprint, FingerprintSet
from tests.integration.src.sqlbuild.compiler.fingerprints.main._test_types import (
    InvalidDefinitionStorageTestCase,
    LatestResolutionTestCase,
    OldFingerprintSchemaTestCase,
    PruneFingerprintHistoryTestCase,
    ReadNonExistentTableTestCase,
    WriteAndReadTestCase,
    WriteCreatesTableTestCase,
)

RENDER_QUALIFIED_NAME: Callable[..., str | None] = DuckDbAdapter().render_qualified_name
RENDER_FRAMEWORK_TYPE: Callable[[FrameworkType], str] = DuckDbAdapter().render_framework_type
RENDER_READ_LATEST_SQL: Callable[..., str] = DuckDbAdapter().render_read_latest_fingerprints_sql
RELATION_EXISTS: Callable[..., bool] = DuckDbAdapter().relation_exists

WRITE_AND_READ_TEST_CASES: list[WriteAndReadTestCase] = [
    WriteAndReadTestCase(
        description="writes and reads back a single fingerprint",
        database=None,
        schema="test_schema",
        fingerprints=(
            Fingerprint(
                node_type="model",
                node_name="orders",
                target_database=None,
                target_schema=None,
                target_name="orders",
                run_id="run_001",
                definition_hash="hash_a",
                version_hash="version_a",
                schema_fingerprint="schema_a",
                definition="SELECT id FROM orders",
                ts=datetime(2026, 1, 15, 12, 0, 0),
            ),
        ),
        expected_node_names=("orders",),
        expected_latest_definition_hashes={"orders": "hash_a"},
        expected_latest_target_names={"orders": "orders"},
    ),
    WriteAndReadTestCase(
        description="writes and reads fingerprints for multiple models",
        database=None,
        schema="test_schema",
        fingerprints=(
            Fingerprint(
                node_type="model",
                node_name="orders",
                target_database=None,
                target_schema=None,
                target_name="orders",
                run_id="run_001",
                definition_hash="hash_a",
                version_hash="version_a",
                schema_fingerprint="schema_a",
                definition="SELECT id FROM orders",
                ts=datetime(2026, 1, 15, 12, 0, 0),
            ),
            Fingerprint(
                node_type="model",
                node_name="customers",
                target_database=None,
                target_schema=None,
                target_name="customers",
                run_id="run_001",
                definition_hash="hash_b",
                version_hash="version_b",
                schema_fingerprint="schema_b",
                definition="SELECT id FROM customers",
                ts=datetime(2026, 1, 15, 12, 0, 0),
            ),
        ),
        expected_node_names=("customers", "orders"),
        expected_latest_definition_hashes={"orders": "hash_a", "customers": "hash_b"},
        expected_latest_target_names={"orders": "orders", "customers": "customers"},
    ),
    WriteAndReadTestCase(
        description="writes and reads multiline query sql with quotes and backslashes",
        database=None,
        schema="test_schema",
        fingerprints=(
            Fingerprint(
                node_type="model",
                node_name="orders",
                target_database=None,
                target_schema=None,
                target_name="orders",
                run_id="run_001",
                definition_hash="hash_a",
                version_hash="version_a",
                schema_fingerprint="schema_a",
                definition="SELECT '\\n' AS slash_n\nFROM orders\nWHERE note = 'line\\nvalue'",
                ts=datetime(2026, 1, 15, 12, 0, 0),
            ),
        ),
        expected_node_names=("orders",),
        expected_latest_definition_hashes={"orders": "hash_a"},
        expected_latest_target_names={"orders": "orders"},
    ),
    WriteAndReadTestCase(
        description="writes and reads audit gate metadata from fingerprint storage",
        database=None,
        schema="test_schema",
        fingerprints=(
            Fingerprint(
                node_type="model",
                node_name="orders",
                target_database=None,
                target_schema=None,
                target_name="orders",
                run_id="run_001",
                definition_hash="hash_a",
                version_hash="version_a",
                schema_fingerprint="schema_a",
                definition="SELECT id FROM orders",
                metadata_json=json.dumps(
                    {
                        "audit_gate": {
                            "status": "passed",
                            "binding_set_hash": "binding_hash",
                            "blocking_set_hash": "blocking_hash",
                            "mode": "executed",
                            "run_id": "run_001",
                            "results": [
                                {
                                    "binding_key": "binding_key",
                                    "audit_name": "not_null_orders",
                                    "definition_fingerprint": "definition_hash",
                                    "execution_fingerprint": "execution_hash",
                                    "severity": "error",
                                    "run_scope_phase": "final",
                                    "outcome": "pass",
                                    "row_count": 0,
                                    "attached_target_name": "orders",
                                    "attached_column_name": "order_id",
                                }
                            ],
                        },
                        "config": {"materialized": "table"},
                    },
                    sort_keys=True,
                    separators=(",", ":"),
                ),
                ts=datetime(2026, 1, 15, 12, 0, 0),
            ),
        ),
        expected_node_names=("orders",),
        expected_latest_definition_hashes={"orders": "hash_a"},
        expected_latest_target_names={"orders": "orders"},
        expected_metadata_fragments=(
            '"audit_gate":{"binding_set_hash":"binding_hash"',
            '"execution_fingerprint":"execution_hash"',
            '"attached_column_name":"order_id"',
        ),
    ),
]

LATEST_RESOLUTION_TEST_CASES: list[LatestResolutionTestCase] = [
    LatestResolutionTestCase(
        description="resolves latest fingerprint when older row is inserted after newer",
        database=None,
        schema="test_schema",
        fingerprints=(
            Fingerprint(
                node_type="model",
                node_name="orders",
                target_database=None,
                target_schema=None,
                target_name="orders",
                run_id="run_002",
                definition_hash="new_hash",
                version_hash="new_version",
                schema_fingerprint="new_schema",
                definition="SELECT 2",
                ts=datetime(2026, 1, 15, 12, 0, 0),
            ),
            Fingerprint(
                node_type="model",
                node_name="orders",
                target_database=None,
                target_schema=None,
                target_name="orders",
                run_id="run_001",
                definition_hash="old_hash",
                version_hash="old_version",
                schema_fingerprint="old_schema",
                definition="SELECT 1",
                ts=datetime(2026, 1, 15, 10, 0, 0),
            ),
        ),
        expected_latest_run_id="run_002",
        expected_latest_definition_hash="new_hash",
        expected_latest_definition="SELECT 2",
    ),
    LatestResolutionTestCase(
        description="resolves latest fingerprint by run id when timestamps tie",
        database=None,
        schema="test_schema",
        fingerprints=(
            Fingerprint(
                node_type="model",
                node_name="orders",
                target_database=None,
                target_schema=None,
                target_name="orders",
                run_id="run_001",
                definition_hash="low_run_hash",
                version_hash="low_run_version",
                schema_fingerprint="low_run_schema",
                definition="SELECT 1",
                ts=datetime(2026, 1, 15, 12, 0, 0),
            ),
            Fingerprint(
                node_type="model",
                node_name="orders",
                target_database=None,
                target_schema=None,
                target_name="orders",
                run_id="run_002",
                definition_hash="high_run_hash",
                version_hash="high_run_version",
                schema_fingerprint="high_run_schema",
                definition="SELECT 2",
                ts=datetime(2026, 1, 15, 12, 0, 0),
            ),
        ),
        expected_latest_run_id="run_002",
        expected_latest_definition_hash="high_run_hash",
        expected_latest_definition="SELECT 2",
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
        relation_exists=RELATION_EXISTS,
        database=test_case.database,
        schema=test_case.schema,
        render_qualified_name=RENDER_QUALIFIED_NAME,
        render_read_latest_sql=RENDER_READ_LATEST_SQL,
    )

    assert tuple(sorted(result.fingerprints.keys())) == test_case.expected_node_names
    node_name: str
    expected_hash: str
    for node_name, expected_hash in test_case.expected_latest_definition_hashes.items():
        assert result.fingerprints[node_name].definition_hash == expected_hash
    expected_target_name: str | None
    for node_name, expected_target_name in test_case.expected_latest_target_names.items():
        assert result.fingerprints[node_name].target_name == expected_target_name
    fp: Fingerprint
    for fp in test_case.fingerprints:
        assert result.fingerprints[fp.node_name].definition == fp.definition
        assert result.fingerprints[fp.node_name].version_hash == fp.version_hash
    fragment: str
    for fragment in test_case.expected_metadata_fragments:
        assert fragment in result.fingerprints[test_case.expected_node_names[0]].metadata_json


@pytest.mark.parametrize(
    "test_case",
    [
        ReadNonExistentTableTestCase(
            description="returns empty set when fingerprint table does not exist",
            database=None,
            schema="test_schema",
            expected_node_count=0,
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
        relation_exists=RELATION_EXISTS,
        database=test_case.database,
        schema=test_case.schema,
        render_qualified_name=RENDER_QUALIFIED_NAME,
        render_read_latest_sql=RENDER_READ_LATEST_SQL,
    )

    assert len(result.fingerprints) == test_case.expected_node_count


@pytest.mark.parametrize(
    "test_case",
    [
        OldFingerprintSchemaTestCase(
            description="old fingerprint table without version hash raises upgrade guidance",
            schema="old_fingerprint_schema",
            expected_error_fragments=(
                "Unable to read fingerprints from old_fingerprint_schema._sqlbuild_fingerprints",
                "upgrading from an older sqlbuild version",
                "delete or rebuild the SQLBuild fingerprint table",
            ),
        )
    ],
    ids=["old fingerprint table without version hash raises upgrade guidance"],
)
def test_given_old_fingerprint_table_without_version_hash_when_reading_then_raises_upgrade_guidance(
    test_case: OldFingerprintSchemaTestCase,
    connection: Any,
    execute: Any,
) -> None:
    schema: str = test_case.schema
    connection.execute(f"CREATE SCHEMA IF NOT EXISTS {schema}")
    connection.execute(
        f"CREATE TABLE {schema}.{FINGERPRINT_TABLE_NAME} ("
        "model_name VARCHAR NOT NULL, "
        "target_database VARCHAR, "
        "target_schema VARCHAR, "
        "target_name VARCHAR, "
        "run_id VARCHAR NOT NULL, "
        "query_hash VARCHAR NOT NULL, "
        "schema_fingerprint VARCHAR NOT NULL, "
        "query_sql_b64 VARCHAR NOT NULL, "
        "metadata_json_b64 VARCHAR NOT NULL, "
        "ts TIMESTAMP NOT NULL)"
    )
    connection.execute(
        f"INSERT INTO {schema}.{FINGERPRINT_TABLE_NAME} VALUES (?, NULL, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            "orders",
            schema,
            "orders",
            "run_001",
            "hash_a",
            "schema_a",
            "U0VMRUNUIDo=",
            "e30=",
            datetime(2026, 1, 15, 12, 0, 0),
        ),
    )

    with pytest.raises(ValueError) as error_info:
        read_latest_fingerprints(
            connection=connection,
            execute=execute,
            relation_exists=RELATION_EXISTS,
            database=None,
            schema=schema,
            render_qualified_name=RENDER_QUALIFIED_NAME,
            render_read_latest_sql=RENDER_READ_LATEST_SQL,
        )

    message: str = str(error_info.value)
    fragment: str
    for fragment in test_case.expected_error_fragments:
        assert fragment in message


@pytest.mark.parametrize(
    "test_case",
    [
        WriteCreatesTableTestCase(
            description="write creates table if it does not exist",
            database=None,
            schema="test_schema",
            fingerprint=Fingerprint(
                node_type="model",
                node_name="orders",
                target_database=None,
                target_schema=None,
                target_name="orders",
                run_id="run_001",
                definition_hash="hash_a",
                version_hash="version_a",
                schema_fingerprint="schema_a",
                definition="SELECT 1",
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
    column_row: Any = connection.execute(
        "SELECT 1 FROM information_schema.columns "
        f"WHERE table_schema = '{test_case.schema}' "
        f"AND table_name = '{FINGERPRINT_TABLE_NAME}' "
        "AND column_name = 'definition_b64'"
    ).fetchone()
    assert column_row is not None


@pytest.mark.parametrize(
    "test_case",
    LATEST_RESOLUTION_TEST_CASES,
    ids=[case.description for case in LATEST_RESOLUTION_TEST_CASES],
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
        relation_exists=RELATION_EXISTS,
        database=test_case.database,
        schema=test_case.schema,
        render_qualified_name=RENDER_QUALIFIED_NAME,
        render_read_latest_sql=RENDER_READ_LATEST_SQL,
    )
    latest: Fingerprint = result.fingerprints["orders"]

    assert latest.run_id == test_case.expected_latest_run_id
    assert latest.definition_hash == test_case.expected_latest_definition_hash
    assert latest.definition == test_case.expected_latest_definition


@pytest.mark.parametrize(
    "test_case",
    [
        PruneFingerprintHistoryTestCase(
            description="prunes fingerprint history by node and run id tie breaker",
            database=None,
            schema="test_schema",
            retain_versions=2,
            fingerprints=(
                Fingerprint(
                    node_type="model",
                    node_name="orders",
                    target_database=None,
                    target_schema=None,
                    target_name="orders",
                    run_id="run_000",
                    definition_hash="hash_old",
                    version_hash="version_old",
                    schema_fingerprint="schema_old",
                    definition="SELECT 0",
                    ts=datetime(2026, 1, 15, 10, 0, 0),
                ),
                Fingerprint(
                    node_type="model",
                    node_name="orders",
                    target_database=None,
                    target_schema=None,
                    target_name="orders",
                    run_id="run_001",
                    definition_hash="hash_low_tie",
                    version_hash="version_low_tie",
                    schema_fingerprint="schema_low_tie",
                    definition="SELECT 1",
                    ts=datetime(2026, 1, 15, 12, 0, 0),
                ),
                Fingerprint(
                    node_type="model",
                    node_name="orders",
                    target_database=None,
                    target_schema=None,
                    target_name="orders",
                    run_id="run_002",
                    definition_hash="hash_high_tie",
                    version_hash="version_high_tie",
                    schema_fingerprint="schema_high_tie",
                    definition="SELECT 2",
                    ts=datetime(2026, 1, 15, 12, 0, 0),
                ),
                Fingerprint(
                    node_type="model",
                    node_name="orders",
                    target_database=None,
                    target_schema=None,
                    target_name="orders",
                    run_id="run_003",
                    definition_hash="hash_latest",
                    version_hash="version_latest",
                    schema_fingerprint="schema_latest",
                    definition="SELECT 3",
                    ts=datetime(2026, 1, 15, 13, 0, 0),
                ),
                Fingerprint(
                    node_type="model",
                    node_name="customers",
                    target_database=None,
                    target_schema=None,
                    target_name="customers",
                    run_id="run_010",
                    definition_hash="hash_customers_old",
                    version_hash="version_customers_old",
                    schema_fingerprint="schema_customers_old",
                    definition="SELECT 10",
                    ts=datetime(2026, 1, 15, 10, 0, 0),
                ),
                Fingerprint(
                    node_type="model",
                    node_name="customers",
                    target_database=None,
                    target_schema=None,
                    target_name="customers",
                    run_id="run_011",
                    definition_hash="hash_customers_latest",
                    version_hash="version_customers_latest",
                    schema_fingerprint="schema_customers_latest",
                    definition="SELECT 11",
                    ts=datetime(2026, 1, 15, 11, 0, 0),
                ),
            ),
            expected_run_ids_by_node={
                "orders": ("run_003", "run_002"),
                "customers": ("run_011", "run_010"),
            },
            expected_latest_run_id="run_003",
        )
    ],
    ids=["prunes fingerprint history by node and run id tie breaker"],
)
def test_given_fingerprint_history_when_pruning_then_keeps_latest_versions_per_node(
    test_case: PruneFingerprintHistoryTestCase,
    adapter: DuckDbAdapter,
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

    execute(
        connection,
        adapter.render_prune_fingerprint_history_sql(
            database=test_case.database,
            schema=test_case.schema,
            retain_versions=test_case.retain_versions,
        ),
    )

    node_name: str
    expected_run_ids: tuple[str, ...]
    for node_name, expected_run_ids in test_case.expected_run_ids_by_node.items():
        rows: list[tuple[str]] = connection.execute(
            f"SELECT run_id FROM {test_case.schema}.{FINGERPRINT_TABLE_NAME} "
            "WHERE node_name = ? ORDER BY ts DESC, run_id DESC",
            (node_name,),
        ).fetchall()
        assert tuple(row[0] for row in rows) == expected_run_ids
    latest_result: FingerprintSet = read_latest_fingerprints(
        connection=connection,
        execute=execute,
        relation_exists=RELATION_EXISTS,
        database=test_case.database,
        schema=test_case.schema,
        render_qualified_name=RENDER_QUALIFIED_NAME,
        render_read_latest_sql=RENDER_READ_LATEST_SQL,
    )
    assert latest_result.fingerprints["orders"].run_id == test_case.expected_latest_run_id


@pytest.mark.parametrize(
    "test_case",
    [
        InvalidDefinitionStorageTestCase(
            description="invalid definition b64 storage raises contextual error",
            schema="test_schema",
            node_name="orders",
            raw_definition_storage="SELECT 1",
            expected_error_fragments=(
                "Invalid fingerprint definition storage for 'orders'",
                "expected base64-encoded UTF-8",
                "delete or rebuild",
                "_sqlbuild_fingerprints",
            ),
        )
    ],
    ids=["invalid definition b64 storage raises contextual error"],
)
def test_given_invalid_definition_storage_when_reading_then_raises_contextual_error(
    test_case: InvalidDefinitionStorageTestCase,
    connection: Any,
    execute: Any,
) -> None:
    connection.execute(f"CREATE SCHEMA IF NOT EXISTS {test_case.schema}")
    connection.execute(
        f"CREATE TABLE {test_case.schema}.{FINGERPRINT_TABLE_NAME} ("
        "node_type VARCHAR NOT NULL, "
        "node_name VARCHAR NOT NULL, "
        "target_database VARCHAR, "
        "target_schema VARCHAR, "
        "target_name VARCHAR, "
        "run_id VARCHAR NOT NULL, "
        "definition_hash VARCHAR NOT NULL, "
        "version_hash VARCHAR NOT NULL, "
        "schema_fingerprint VARCHAR NOT NULL, "
        "definition_b64 VARCHAR NOT NULL, "
        "metadata_json_b64 VARCHAR NOT NULL, "
        "ts TIMESTAMP NOT NULL)"
    )
    connection.execute(
        f"INSERT INTO {test_case.schema}.{FINGERPRINT_TABLE_NAME} VALUES "
        "(?, ?, NULL, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            "model",
            test_case.node_name,
            test_case.schema,
            test_case.node_name,
            "run_001",
            "hash_a",
            "version_a",
            "schema_a",
            test_case.raw_definition_storage,
            "e30=",
            datetime(2026, 1, 15, 12, 0, 0),
        ),
    )

    with pytest.raises(ValueError) as error_info:
        read_latest_fingerprints(
            connection=connection,
            execute=execute,
            relation_exists=RELATION_EXISTS,
            database=None,
            schema=test_case.schema,
            render_qualified_name=RENDER_QUALIFIED_NAME,
            render_read_latest_sql=RENDER_READ_LATEST_SQL,
        )

    message: str = str(error_info.value)
    fragment: str
    for fragment in test_case.expected_error_fragments:
        assert fragment in message
