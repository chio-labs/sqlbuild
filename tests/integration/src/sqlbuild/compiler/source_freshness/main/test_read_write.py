from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Any

import pytest

from sqlbuild.adapter.shared.types import FrameworkType
from sqlbuild.adapters.duckdb.client import DuckDbAdapter
from sqlbuild.compiler.source_freshness.constants import SOURCE_FRESHNESS_TABLE_NAME
from sqlbuild.compiler.source_freshness.main.read import read_latest_source_freshness
from sqlbuild.compiler.source_freshness.main.write import write_source_freshness_records
from sqlbuild.compiler.source_freshness.models import (
    SourceFreshnessIdentity,
    SourceFreshnessRecord,
    SourceFreshnessSet,
)
from tests.integration.src.sqlbuild.compiler.source_freshness.main._test_types import (
    SourceFreshnessLatestResolutionTestCase,
    SourceFreshnessPruneHistoryTestCase,
    SourceFreshnessReadNonExistentTableTestCase,
    SourceFreshnessRoundTripTestCase,
    SourceFreshnessWriteAndReadTestCase,
    SourceFreshnessWriteCreatesTableTestCase,
)

RENDER_QUALIFIED_NAME: Callable[..., str | None] = DuckDbAdapter().render_qualified_name
RENDER_FRAMEWORK_TYPE: Callable[[FrameworkType], str] = DuckDbAdapter().render_framework_type
RENDER_READ_LATEST_SQL: Callable[..., str] = DuckDbAdapter().render_read_latest_source_freshness_sql
RENDER_INSERT_RECORDS_SQL: Callable[..., str] = (
    DuckDbAdapter().render_insert_source_freshness_records_sql
)
RELATION_EXISTS: Callable[..., bool] = DuckDbAdapter().relation_exists

SOURCE_FRESHNESS_ROUND_TRIP_TEST_CASES: list[SourceFreshnessRoundTripTestCase] = [
    SourceFreshnessRoundTripTestCase(
        description="round trips null data version",
        database=None,
        schema="test_schema",
        records=(
            SourceFreshnessRecord(
                source_name="raw.unknown_orders",
                target_database=None,
                target_schema="raw",
                target_name="unknown_orders",
                run_id="run_001",
                strategy="unknown",
                value_kind="unknown",
                data_version=None,
                data_version_hash="unknown_hash",
                observed_at=datetime(2026, 1, 15, 12, 5, 0),
            ),
        ),
        expected_data_version=None,
        expected_data_version_hash="unknown_hash",
    ),
    SourceFreshnessRoundTripTestCase(
        description="round trips quoted source freshness values",
        database=None,
        schema="test_schema",
        records=(
            SourceFreshnessRecord(
                source_name="raw.o'rders",
                target_database=None,
                target_schema="r'aw",
                target_name="o'rders",
                run_id="run_'001",
                strategy="adapter_'metadata",
                value_kind="time'stamp",
                data_version="2026-01-15T12:00:00's",
                data_version_hash="hash_'orders",
                observed_at=datetime(2026, 1, 15, 12, 5, 0),
            ),
        ),
        expected_data_version="2026-01-15T12:00:00's",
        expected_data_version_hash="hash_'orders",
    ),
]

SOURCE_FRESHNESS_LATEST_RESOLUTION_TEST_CASES: list[SourceFreshnessLatestResolutionTestCase] = [
    SourceFreshnessLatestResolutionTestCase(
        description="resolves latest source freshness when older row is inserted after newer",
        database=None,
        schema="test_schema",
        records=(
            SourceFreshnessRecord(
                source_name="raw.orders",
                target_database=None,
                target_schema="raw",
                target_name="orders",
                run_id="run_002",
                strategy="adapter_metadata",
                value_kind="timestamp",
                data_version="2026-01-15T12:00:00",
                data_version_hash="new_hash",
                observed_at=datetime(2026, 1, 15, 12, 5, 0),
            ),
            SourceFreshnessRecord(
                source_name="raw.orders",
                target_database=None,
                target_schema="raw",
                target_name="orders",
                run_id="run_001",
                strategy="adapter_metadata",
                value_kind="timestamp",
                data_version="2026-01-15T10:00:00",
                data_version_hash="old_hash",
                observed_at=datetime(2026, 1, 15, 10, 5, 0),
            ),
        ),
        identity=SourceFreshnessIdentity("raw.orders", None, "raw", "orders"),
        expected_latest_run_id="run_002",
        expected_latest_data_version_hash="new_hash",
        expected_latest_data_version="2026-01-15T12:00:00",
    ),
    SourceFreshnessLatestResolutionTestCase(
        description="resolves latest source freshness by run id when observed_at ties",
        database=None,
        schema="test_schema",
        records=(
            SourceFreshnessRecord(
                source_name="raw.orders",
                target_database=None,
                target_schema="raw",
                target_name="orders",
                run_id="run_001",
                strategy="adapter_metadata",
                value_kind="timestamp",
                data_version="2026-01-15T10:00:00",
                data_version_hash="low_run_hash",
                observed_at=datetime(2026, 1, 15, 12, 5, 0),
            ),
            SourceFreshnessRecord(
                source_name="raw.orders",
                target_database=None,
                target_schema="raw",
                target_name="orders",
                run_id="run_002",
                strategy="adapter_metadata",
                value_kind="timestamp",
                data_version="2026-01-15T12:00:00",
                data_version_hash="high_run_hash",
                observed_at=datetime(2026, 1, 15, 12, 5, 0),
            ),
        ),
        identity=SourceFreshnessIdentity("raw.orders", None, "raw", "orders"),
        expected_latest_run_id="run_002",
        expected_latest_data_version_hash="high_run_hash",
        expected_latest_data_version="2026-01-15T12:00:00",
    ),
]

SOURCE_FRESHNESS_IDENTITY_TEST_CASES: list[SourceFreshnessWriteAndReadTestCase] = [
    SourceFreshnessWriteAndReadTestCase(
        description="keeps same source name separate by target identity",
        database=None,
        schema="test_schema",
        records=(
            SourceFreshnessRecord(
                source_name="raw.orders",
                target_database=None,
                target_schema="raw_dev",
                target_name="orders",
                run_id="run_001",
                strategy="adapter_metadata",
                value_kind="timestamp",
                data_version="2026-01-15T10:00:00",
                data_version_hash="dev_hash",
                observed_at=datetime(2026, 1, 15, 10, 5, 0),
            ),
            SourceFreshnessRecord(
                source_name="raw.orders",
                target_database=None,
                target_schema="raw_prod",
                target_name="orders",
                run_id="run_002",
                strategy="adapter_metadata",
                value_kind="timestamp",
                data_version="2026-01-15T12:00:00",
                data_version_hash="prod_hash",
                observed_at=datetime(2026, 1, 15, 12, 5, 0),
            ),
        ),
        expected_identities=(
            SourceFreshnessIdentity("raw.orders", None, "raw_dev", "orders"),
            SourceFreshnessIdentity("raw.orders", None, "raw_prod", "orders"),
        ),
        expected_latest_hashes={
            SourceFreshnessIdentity("raw.orders", None, "raw_dev", "orders"): "dev_hash",
            SourceFreshnessIdentity("raw.orders", None, "raw_prod", "orders"): "prod_hash",
        },
        expected_latest_target_names={
            SourceFreshnessIdentity("raw.orders", None, "raw_dev", "orders"): "orders",
            SourceFreshnessIdentity("raw.orders", None, "raw_prod", "orders"): "orders",
        },
    ),
    SourceFreshnessWriteAndReadTestCase(
        description="keeps null target identity separate from physical target identity",
        database=None,
        schema="test_schema",
        records=(
            SourceFreshnessRecord(
                source_name="raw.orders",
                target_database=None,
                target_schema=None,
                target_name=None,
                run_id="run_001",
                strategy="adapter_metadata",
                value_kind="timestamp",
                data_version="2026-01-15T10:00:00",
                data_version_hash="null_target_hash",
                observed_at=datetime(2026, 1, 15, 10, 5, 0),
            ),
            SourceFreshnessRecord(
                source_name="raw.orders",
                target_database=None,
                target_schema="raw",
                target_name="orders",
                run_id="run_002",
                strategy="adapter_metadata",
                value_kind="timestamp",
                data_version="2026-01-15T12:00:00",
                data_version_hash="physical_target_hash",
                observed_at=datetime(2026, 1, 15, 12, 5, 0),
            ),
        ),
        expected_identities=(
            SourceFreshnessIdentity("raw.orders", None, "raw", "orders"),
            SourceFreshnessIdentity("raw.orders", None, None, None),
        ),
        expected_latest_hashes={
            SourceFreshnessIdentity("raw.orders", None, None, None): "null_target_hash",
            SourceFreshnessIdentity("raw.orders", None, "raw", "orders"): ("physical_target_hash"),
        },
        expected_latest_target_names={
            SourceFreshnessIdentity("raw.orders", None, None, None): None,
            SourceFreshnessIdentity("raw.orders", None, "raw", "orders"): "orders",
        },
    ),
]


@pytest.mark.parametrize(
    "test_case",
    [
        SourceFreshnessWriteAndReadTestCase(
            description="writes and reads source freshness for multiple sources",
            database=None,
            schema="test_schema",
            records=(
                SourceFreshnessRecord(
                    source_name="raw.orders",
                    target_database=None,
                    target_schema="raw",
                    target_name="orders",
                    run_id="run_001",
                    strategy="adapter_metadata",
                    value_kind="timestamp",
                    data_version="2026-01-15T12:00:00",
                    data_version_hash="hash_orders",
                    observed_at=datetime(2026, 1, 15, 12, 5, 0),
                ),
                SourceFreshnessRecord(
                    source_name="raw.customers",
                    target_database=None,
                    target_schema="raw",
                    target_name="customers",
                    run_id="run_001",
                    strategy="adapter_metadata",
                    value_kind="timestamp",
                    data_version="2026-01-15T12:01:00",
                    data_version_hash="hash_customers",
                    observed_at=datetime(2026, 1, 15, 12, 6, 0),
                ),
            ),
            expected_identities=(
                SourceFreshnessIdentity("raw.customers", None, "raw", "customers"),
                SourceFreshnessIdentity("raw.orders", None, "raw", "orders"),
            ),
            expected_latest_hashes={
                SourceFreshnessIdentity("raw.orders", None, "raw", "orders"): "hash_orders",
                SourceFreshnessIdentity(
                    "raw.customers", None, "raw", "customers"
                ): "hash_customers",
            },
            expected_latest_target_names={
                SourceFreshnessIdentity("raw.orders", None, "raw", "orders"): "orders",
                SourceFreshnessIdentity("raw.customers", None, "raw", "customers"): "customers",
            },
        )
    ],
    ids=["writes and reads source freshness for multiple sources"],
)
def test_given_source_freshness_records_when_writing_and_reading_then_returns_expected(
    test_case: SourceFreshnessWriteAndReadTestCase,
    connection: Any,
    execute: Any,
) -> None:
    write_source_freshness_records(
        connection=connection,
        execute=execute,
        database=test_case.database,
        schema=test_case.schema,
        records=test_case.records,
        render_qualified_name=RENDER_QUALIFIED_NAME,
        render_framework_type=RENDER_FRAMEWORK_TYPE,
        render_insert_records_sql=RENDER_INSERT_RECORDS_SQL,
    )

    result: SourceFreshnessSet = read_latest_source_freshness(
        connection=connection,
        execute=execute,
        table_exists=RELATION_EXISTS(
            connection,
            database=test_case.database,
            schema=test_case.schema,
            name=SOURCE_FRESHNESS_TABLE_NAME,
        ),
        database=test_case.database,
        schema=test_case.schema,
        render_qualified_name=RENDER_QUALIFIED_NAME,
        render_read_latest_sql=RENDER_READ_LATEST_SQL,
    )

    assert tuple(sorted(result.records.keys(), key=str)) == test_case.expected_identities
    identity: SourceFreshnessIdentity
    expected_hash: str
    for identity, expected_hash in test_case.expected_latest_hashes.items():
        assert result.records[identity].data_version_hash == expected_hash
    expected_target_name: str | None
    for identity, expected_target_name in test_case.expected_latest_target_names.items():
        assert result.records[identity].target_name == expected_target_name


@pytest.mark.parametrize(
    "test_case",
    [
        SourceFreshnessReadNonExistentTableTestCase(
            description="returns empty set when source freshness table does not exist",
            database=None,
            schema="test_schema",
            expected_record_count=0,
        )
    ],
    ids=["returns empty set when source freshness table does not exist"],
)
def test_given_no_table_when_reading_source_freshness_then_returns_empty_set(
    test_case: SourceFreshnessReadNonExistentTableTestCase,
    connection: Any,
    execute: Any,
) -> None:
    result: SourceFreshnessSet = read_latest_source_freshness(
        connection=connection,
        execute=execute,
        table_exists=RELATION_EXISTS(
            connection,
            database=test_case.database,
            schema=test_case.schema,
            name=SOURCE_FRESHNESS_TABLE_NAME,
        ),
        database=test_case.database,
        schema=test_case.schema,
        render_qualified_name=RENDER_QUALIFIED_NAME,
        render_read_latest_sql=RENDER_READ_LATEST_SQL,
    )

    assert len(result.records) == test_case.expected_record_count


@pytest.mark.parametrize(
    "test_case",
    [
        SourceFreshnessWriteCreatesTableTestCase(
            description="write creates source freshness table if it does not exist",
            database=None,
            schema="test_schema",
            records=(
                SourceFreshnessRecord(
                    source_name="raw.orders",
                    target_database=None,
                    target_schema="raw",
                    target_name="orders",
                    run_id="run_001",
                    strategy="adapter_metadata",
                    value_kind="timestamp",
                    data_version="2026-01-15T12:00:00",
                    data_version_hash="hash_orders",
                    observed_at=datetime(2026, 1, 15, 12, 5, 0),
                ),
            ),
            expected_table_exists=True,
        )
    ],
    ids=["write creates source freshness table if it does not exist"],
)
def test_given_no_table_when_writing_source_freshness_then_creates_table(
    test_case: SourceFreshnessWriteCreatesTableTestCase,
    connection: Any,
    execute: Any,
) -> None:
    write_source_freshness_records(
        connection=connection,
        execute=execute,
        database=test_case.database,
        schema=test_case.schema,
        records=test_case.records,
        render_qualified_name=RENDER_QUALIFIED_NAME,
        render_framework_type=RENDER_FRAMEWORK_TYPE,
        render_insert_records_sql=RENDER_INSERT_RECORDS_SQL,
    )

    row: Any = connection.execute(
        f"SELECT 1 FROM information_schema.tables "
        f"WHERE table_schema = '{test_case.schema}' "
        f"AND table_name = '{SOURCE_FRESHNESS_TABLE_NAME}'"
    ).fetchone()
    assert (row is not None) == test_case.expected_table_exists
    column_row: Any = connection.execute(
        "SELECT 1 FROM information_schema.columns "
        f"WHERE table_schema = '{test_case.schema}' "
        f"AND table_name = '{SOURCE_FRESHNESS_TABLE_NAME}' "
        "AND column_name = 'data_version_hash'"
    ).fetchone()
    assert column_row is not None


@pytest.mark.parametrize(
    "test_case",
    SOURCE_FRESHNESS_LATEST_RESOLUTION_TEST_CASES,
    ids=[case.description for case in SOURCE_FRESHNESS_LATEST_RESOLUTION_TEST_CASES],
)
def test_given_multiple_source_freshness_records_when_reading_then_resolves_latest(
    test_case: SourceFreshnessLatestResolutionTestCase,
    connection: Any,
    execute: Any,
) -> None:
    write_source_freshness_records(
        connection=connection,
        execute=execute,
        database=test_case.database,
        schema=test_case.schema,
        records=test_case.records,
        render_qualified_name=RENDER_QUALIFIED_NAME,
        render_framework_type=RENDER_FRAMEWORK_TYPE,
        render_insert_records_sql=RENDER_INSERT_RECORDS_SQL,
    )

    result: SourceFreshnessSet = read_latest_source_freshness(
        connection=connection,
        execute=execute,
        table_exists=RELATION_EXISTS(
            connection,
            database=test_case.database,
            schema=test_case.schema,
            name=SOURCE_FRESHNESS_TABLE_NAME,
        ),
        database=test_case.database,
        schema=test_case.schema,
        render_qualified_name=RENDER_QUALIFIED_NAME,
        render_read_latest_sql=RENDER_READ_LATEST_SQL,
    )
    latest: SourceFreshnessRecord = result.records[test_case.identity]

    assert latest.run_id == test_case.expected_latest_run_id
    assert latest.data_version_hash == test_case.expected_latest_data_version_hash
    assert latest.data_version == test_case.expected_latest_data_version


@pytest.mark.parametrize(
    "test_case",
    [
        SourceFreshnessPruneHistoryTestCase(
            description="prunes source freshness history by full identity and run id tie breaker",
            database=None,
            schema="test_schema",
            retain_versions=2,
            records=(
                SourceFreshnessRecord(
                    source_name="raw.orders",
                    target_database=None,
                    target_schema=None,
                    target_name=None,
                    run_id="run_000",
                    strategy="adapter_metadata",
                    value_kind="timestamp",
                    data_version="2026-01-15T10:00:00",
                    data_version_hash="hash_old",
                    observed_at=datetime(2026, 1, 15, 10, 5, 0),
                ),
                SourceFreshnessRecord(
                    source_name="raw.orders",
                    target_database=None,
                    target_schema=None,
                    target_name=None,
                    run_id="run_001",
                    strategy="adapter_metadata",
                    value_kind="timestamp",
                    data_version="2026-01-15T12:00:00",
                    data_version_hash="hash_low_tie",
                    observed_at=datetime(2026, 1, 15, 12, 5, 0),
                ),
                SourceFreshnessRecord(
                    source_name="raw.orders",
                    target_database=None,
                    target_schema=None,
                    target_name=None,
                    run_id="run_002",
                    strategy="adapter_metadata",
                    value_kind="timestamp",
                    data_version="2026-01-15T12:00:00",
                    data_version_hash="hash_high_tie",
                    observed_at=datetime(2026, 1, 15, 12, 5, 0),
                ),
                SourceFreshnessRecord(
                    source_name="raw.orders",
                    target_database=None,
                    target_schema=None,
                    target_name=None,
                    run_id="run_003",
                    strategy="adapter_metadata",
                    value_kind="timestamp",
                    data_version="2026-01-15T13:00:00",
                    data_version_hash="hash_latest",
                    observed_at=datetime(2026, 1, 15, 13, 5, 0),
                ),
                SourceFreshnessRecord(
                    source_name="raw.orders",
                    target_database=None,
                    target_schema="raw",
                    target_name="orders",
                    run_id="run_010",
                    strategy="adapter_metadata",
                    value_kind="timestamp",
                    data_version="2026-01-15T10:00:00",
                    data_version_hash="hash_physical_old",
                    observed_at=datetime(2026, 1, 15, 10, 5, 0),
                ),
                SourceFreshnessRecord(
                    source_name="raw.orders",
                    target_database=None,
                    target_schema="raw",
                    target_name="orders",
                    run_id="run_011",
                    strategy="adapter_metadata",
                    value_kind="timestamp",
                    data_version="2026-01-15T11:00:00",
                    data_version_hash="hash_physical_latest",
                    observed_at=datetime(2026, 1, 15, 11, 5, 0),
                ),
            ),
            expected_run_ids_by_identity={
                SourceFreshnessIdentity("raw.orders", None, None, None): (
                    "run_003",
                    "run_002",
                ),
                SourceFreshnessIdentity("raw.orders", None, "raw", "orders"): (
                    "run_011",
                    "run_010",
                ),
            },
            expected_latest_run_id="run_003",
        )
    ],
    ids=["prunes source freshness history by full identity and run id tie breaker"],
)
def test_given_source_freshness_history_when_pruning_then_keeps_latest_versions_per_identity(
    test_case: SourceFreshnessPruneHistoryTestCase,
    adapter: DuckDbAdapter,
    connection: Any,
    execute: Any,
) -> None:
    write_source_freshness_records(
        connection=connection,
        execute=execute,
        database=test_case.database,
        schema=test_case.schema,
        records=test_case.records,
        render_qualified_name=RENDER_QUALIFIED_NAME,
        render_framework_type=RENDER_FRAMEWORK_TYPE,
        render_insert_records_sql=RENDER_INSERT_RECORDS_SQL,
    )

    execute(
        connection,
        adapter.render_prune_source_freshness_history_sql(
            database=test_case.database,
            schema=test_case.schema,
            retain_versions=test_case.retain_versions,
        ),
    )

    identity: SourceFreshnessIdentity
    expected_run_ids: tuple[str, ...]
    for identity, expected_run_ids in test_case.expected_run_ids_by_identity.items():
        rows: list[tuple[str]] = connection.execute(
            f"SELECT run_id FROM {test_case.schema}.{SOURCE_FRESHNESS_TABLE_NAME} "
            "WHERE source_name = ? "
            "AND target_database IS NOT DISTINCT FROM ? "
            "AND target_schema IS NOT DISTINCT FROM ? "
            "AND target_name IS NOT DISTINCT FROM ? "
            "ORDER BY observed_at DESC, run_id DESC",
            (
                identity.source_name,
                identity.target_database,
                identity.target_schema,
                identity.target_name,
            ),
        ).fetchall()
        assert tuple(row[0] for row in rows) == expected_run_ids
    latest_result: SourceFreshnessSet = read_latest_source_freshness(
        connection=connection,
        execute=execute,
        table_exists=RELATION_EXISTS(
            connection,
            database=test_case.database,
            schema=test_case.schema,
            name=SOURCE_FRESHNESS_TABLE_NAME,
        ),
        database=test_case.database,
        schema=test_case.schema,
        render_qualified_name=RENDER_QUALIFIED_NAME,
        render_read_latest_sql=RENDER_READ_LATEST_SQL,
    )
    latest_identity: SourceFreshnessIdentity = SourceFreshnessIdentity(
        "raw.orders", None, None, None
    )
    assert latest_result.records[latest_identity].run_id == test_case.expected_latest_run_id
    row_count: int = connection.execute(
        f"SELECT COUNT(*) FROM {test_case.schema}.{SOURCE_FRESHNESS_TABLE_NAME}"
    ).fetchone()[0]
    assert row_count == sum(
        len(run_ids) for run_ids in test_case.expected_run_ids_by_identity.values()
    )


@pytest.mark.parametrize(
    "test_case",
    SOURCE_FRESHNESS_IDENTITY_TEST_CASES,
    ids=[case.description for case in SOURCE_FRESHNESS_IDENTITY_TEST_CASES],
)
def test_given_same_source_name_with_different_targets_when_reading_then_keeps_identities_separate(
    test_case: SourceFreshnessWriteAndReadTestCase,
    connection: Any,
    execute: Any,
) -> None:
    write_source_freshness_records(
        connection=connection,
        execute=execute,
        database=test_case.database,
        schema=test_case.schema,
        records=test_case.records,
        render_qualified_name=RENDER_QUALIFIED_NAME,
        render_framework_type=RENDER_FRAMEWORK_TYPE,
        render_insert_records_sql=RENDER_INSERT_RECORDS_SQL,
    )

    result: SourceFreshnessSet = read_latest_source_freshness(
        connection=connection,
        execute=execute,
        table_exists=RELATION_EXISTS(
            connection,
            database=test_case.database,
            schema=test_case.schema,
            name=SOURCE_FRESHNESS_TABLE_NAME,
        ),
        database=test_case.database,
        schema=test_case.schema,
        render_qualified_name=RENDER_QUALIFIED_NAME,
        render_read_latest_sql=RENDER_READ_LATEST_SQL,
    )

    assert tuple(sorted(result.records.keys(), key=str)) == test_case.expected_identities
    identity: SourceFreshnessIdentity
    expected_hash: str
    for identity, expected_hash in test_case.expected_latest_hashes.items():
        assert result.records[identity].data_version_hash == expected_hash


@pytest.mark.parametrize(
    "test_case",
    SOURCE_FRESHNESS_ROUND_TRIP_TEST_CASES,
    ids=[case.description for case in SOURCE_FRESHNESS_ROUND_TRIP_TEST_CASES],
)
def test_given_source_freshness_edge_values_when_writing_and_reading_then_round_trips(
    test_case: SourceFreshnessRoundTripTestCase,
    connection: Any,
    execute: Any,
) -> None:
    write_source_freshness_records(
        connection=connection,
        execute=execute,
        database=test_case.database,
        schema=test_case.schema,
        records=test_case.records,
        render_qualified_name=RENDER_QUALIFIED_NAME,
        render_framework_type=RENDER_FRAMEWORK_TYPE,
        render_insert_records_sql=RENDER_INSERT_RECORDS_SQL,
    )

    result: SourceFreshnessSet = read_latest_source_freshness(
        connection=connection,
        execute=execute,
        table_exists=RELATION_EXISTS(
            connection,
            database=test_case.database,
            schema=test_case.schema,
            name=SOURCE_FRESHNESS_TABLE_NAME,
        ),
        database=test_case.database,
        schema=test_case.schema,
        render_qualified_name=RENDER_QUALIFIED_NAME,
        render_read_latest_sql=RENDER_READ_LATEST_SQL,
    )
    latest: SourceFreshnessRecord = result.records[test_case.records[0].identity]

    assert latest.data_version == test_case.expected_data_version
    assert latest.data_version_hash == test_case.expected_data_version_hash
