"""Persisted state identities pinned to the values the Python implementation stored."""

import pytest

from sqlbuild._native import (
    deterministic_column_migration_event_id,
    deterministic_migration_event_id,
    deterministic_old_name_view_event_id,
    source_freshness_data_version_hash,
)
from sqlbuild.compiler.migrations.models import MigrationRelation
from sqlbuild.compiler.migrations.types import OldNameViewEventType
from tests.unit.src.sqlbuild.compiler.migrations.main._test_types import (
    PinnedColumnEventIdTestCase,
    PinnedFreshnessHashTestCase,
    PinnedMoveEventIdTestCase,
    PinnedOldNameEventIdTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    [
        PinnedMoveEventIdTestCase(
            description="move with a database-qualified origin",
            run_id="run-1",
            target_name="prod",
            origin=MigrationRelation(database="Analytics", schema="Staging", name="Orders"),
            destination=MigrationRelation(database=None, schema="Marts", name="orders_v2"),
            expected_event_id="d6b1671e12032fd2efd6b3cd386bb1a7c6ca0fb0b23b70ac7460b35b0cf3eec2",
        ),
        PinnedMoveEventIdTestCase(
            description="move with non-ASCII names and no target",
            run_id="run-\u00fc",
            target_name=None,
            origin=MigrationRelation(database=None, schema=None, name="Stra\u00dfe"),
            destination=MigrationRelation(database="DB", schema="S", name="T"),
            expected_event_id="b35d6666a637e3ceff072be25d1847d304d618808b5d2504d8d3a7a159394d89",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_move_when_hashing_natively_then_matches_stored_python_event_id(
    test_case: PinnedMoveEventIdTestCase,
) -> None:
    event_id: str = deterministic_migration_event_id(
        run_id=test_case.run_id,
        target_name=test_case.target_name,
        origin=test_case.origin,
        destination=test_case.destination,
    )

    assert event_id == test_case.expected_event_id


@pytest.mark.parametrize(
    "test_case",
    [
        PinnedColumnEventIdTestCase(
            description="column rename on a qualified relation",
            relation=MigrationRelation(database="Analytics", schema="Marts", name="Orders"),
            origin_column="Customer_ID",
            destination_column="customer_key",
            expected_event_id="3c7209754b53f98b38b7dbea44c6a9f019f47cfa79a847edceea535095da352c",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_column_rename_when_hashing_natively_then_matches_stored_python_event_id(
    test_case: PinnedColumnEventIdTestCase,
) -> None:
    event_id: str = deterministic_column_migration_event_id(
        run_id="run-1",
        target_name="prod",
        relation=test_case.relation,
        origin_column=test_case.origin_column,
        destination_column=test_case.destination_column,
    )

    assert event_id == test_case.expected_event_id


@pytest.mark.parametrize(
    "test_case",
    [
        PinnedOldNameEventIdTestCase(
            description="old-name view creation",
            event_type=OldNameViewEventType.VIEW_CREATED,
            migration_event_id="abc123",
            expected_event_id="505320604de24bfcf9ca65ba63d373978bb5a26dedf83ad5917d8c7ab70efa73",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_old_name_step_when_hashing_natively_then_matches_stored_python_event_id(
    test_case: PinnedOldNameEventIdTestCase,
) -> None:
    event_id: str = deterministic_old_name_view_event_id(
        event_type=test_case.event_type, migration_event_id=test_case.migration_event_id
    )

    assert event_id == test_case.expected_event_id


@pytest.mark.parametrize(
    "test_case",
    [
        PinnedFreshnessHashTestCase(
            description="timestamp source freshness version",
            source_name="orders",
            strategy="column",
            value_kind="timestamp",
            data_version="2024-01-01T00:00:00+00:00",
            expected_hash="795f41b1b4ffbca0b6bb0b5da1a4ab3ad7a280c28e27e5289bd3c1a2732c5756",
        ),
        PinnedFreshnessHashTestCase(
            description="string source freshness version with escapes",
            source_name="cli\u00ebnts",
            strategy="sql",
            value_kind="string",
            data_version='v"1',
            expected_hash="7f6e8f6a16da5d7653b75617515e4643961a227202c378b84cba4d18f39a7d12",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_data_version_when_hashing_natively_then_matches_stored_python_hash(
    test_case: PinnedFreshnessHashTestCase,
) -> None:
    data_version_hash: str = source_freshness_data_version_hash(
        source_name=test_case.source_name,
        strategy=test_case.strategy,
        value_kind=test_case.value_kind,
        data_version=test_case.data_version,
    )

    assert data_version_hash == test_case.expected_hash
