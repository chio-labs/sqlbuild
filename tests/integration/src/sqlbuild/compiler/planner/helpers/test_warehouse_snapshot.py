from __future__ import annotations

from datetime import datetime
from typing import Any

import pytest

from sqlbuild.compiler.compile.models import CompiledProject
from sqlbuild.compiler.fingerprints.main.write import write_fingerprint
from sqlbuild.compiler.fingerprints.models import Fingerprint
from sqlbuild.compiler.planner.helpers.warehouse_snapshot import gather_warehouse_snapshot
from sqlbuild.compiler.planner.models import WarehouseSnapshot
from sqlbuild.integrations.duckdb.client import DuckDbAdapter
from tests.integration.src.sqlbuild.compiler.planner.helpers._test_types import (
    GatherEmptySnapshotTestCase,
    GatherWarehouseSnapshotTestCase,
)
from tests.integration.src.sqlbuild.compiler.planner.helpers.helpers import (
    build_project_with_targets,
)

GATHER_SNAPSHOT_TEST_CASES: list[GatherWarehouseSnapshotTestCase] = [
    GatherWarehouseSnapshotTestCase(
        description="gathers relations columns and fingerprints across schemas",
        setup_sql=(
            "CREATE TABLE staging.orders (id INTEGER, name VARCHAR)",
            "CREATE TABLE marts.revenue (amount DECIMAL)",
        ),
        model_targets={"orders": "staging", "revenue": "marts"},
        seed_targets={},
        fingerprints_to_write=(
            (
                "staging",
                Fingerprint(
                    model_name="orders",
                    run_id="run_001",
                    query_hash="hash_a",
                    ast_hash=None,
                    schema_fingerprint="schema_a",
                    query_sql="SELECT 1",
                    ts=datetime(2026, 1, 15, 12, 0, 0),
                ),
            ),
        ),
        expected_relation_names=frozenset({"orders", "revenue"}),
        expected_column_table_names=frozenset({"orders", "revenue"}),
        expected_fingerprint_names=frozenset({"orders"}),
    ),
    GatherWarehouseSnapshotTestCase(
        description="gathers snapshot with seed targets included",
        setup_sql=(
            "CREATE TABLE staging.orders (id INTEGER)",
            "CREATE TABLE staging.country_codes (code VARCHAR)",
        ),
        model_targets={"orders": "staging"},
        seed_targets={"country_codes": "staging"},
        expected_relation_names=frozenset({"orders", "country_codes"}),
        expected_column_table_names=frozenset({"orders", "country_codes"}),
        expected_fingerprint_names=frozenset(),
    ),
]


@pytest.mark.parametrize(
    "test_case",
    GATHER_SNAPSHOT_TEST_CASES,
    ids=[case.description for case in GATHER_SNAPSHOT_TEST_CASES],
)
def test_given_warehouse_state_when_gathering_snapshot_then_returns_expected(
    test_case: GatherWarehouseSnapshotTestCase,
    adapter: DuckDbAdapter,
    connection: Any,
    execute: Any,
) -> None:
    statement: str
    for statement in test_case.setup_sql:
        connection.execute(statement)

    fp_entry: tuple[str, Fingerprint]
    for fp_entry in test_case.fingerprints_to_write:
        write_fingerprint(
            connection=connection,
            execute=execute,
            database=None,
            schema=fp_entry[0],
            fingerprint=fp_entry[1],
        )

    project: CompiledProject = build_project_with_targets(
        model_targets=test_case.model_targets,
        seed_targets=test_case.seed_targets,
    )
    snapshot: WarehouseSnapshot = gather_warehouse_snapshot(
        project=project,
        adapter=adapter,
        connection=connection,
        execute=execute,
    )

    assert frozenset(snapshot.existing_relations.keys()) == test_case.expected_relation_names
    assert frozenset(snapshot.existing_columns.keys()) == test_case.expected_column_table_names
    assert frozenset(snapshot.fingerprints.keys()) == test_case.expected_fingerprint_names


@pytest.mark.parametrize(
    "test_case",
    [
        GatherEmptySnapshotTestCase(
            description="returns empty snapshot when no target schemas exist",
            expected_relation_count=0,
            expected_column_count=0,
            expected_fingerprint_count=0,
        ),
    ],
    ids=["returns empty snapshot when no target schemas exist"],
)
def test_given_no_target_schemas_when_gathering_snapshot_then_returns_empty(
    test_case: GatherEmptySnapshotTestCase,
    adapter: DuckDbAdapter,
    connection: Any,
    execute: Any,
) -> None:
    project: CompiledProject = build_project_with_targets(model_targets={}, seed_targets={})
    snapshot: WarehouseSnapshot = gather_warehouse_snapshot(
        project=project,
        adapter=adapter,
        connection=connection,
        execute=execute,
    )

    assert len(snapshot.existing_relations) == test_case.expected_relation_count
    assert len(snapshot.existing_columns) == test_case.expected_column_count
    assert len(snapshot.fingerprints) == test_case.expected_fingerprint_count
