from __future__ import annotations

from datetime import datetime
from typing import Any

import pytest

from sqlbuild.adapter.models import ColumnInfo
from sqlbuild.adapters.duckdb.classes.duckdb_adapter import DuckDbAdapter
from sqlbuild.compiler.compile.models.core import (
    CompiledObjectKey,
    CompiledProject,
    CompiledRelationLocation,
)
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.fingerprints.main.write import write_fingerprint
from sqlbuild.compiler.fingerprints.models import Fingerprint
from sqlbuild.compiler.planner._helpers.output.plan_entry import gather_source_columns
from sqlbuild.compiler.planner._helpers.warehouse.snapshot import gather_warehouse_snapshot
from sqlbuild.compiler.planner.constants import METADATA_NAME_FILTER_LIMIT
from sqlbuild.compiler.planner.models import ModelCursorSnapshot, WarehouseSnapshot
from tests.integration.src.sqlbuild.compiler.planner._helpers._test_types import (
    GatherCursorSnapshotTestCase,
    GatherEmptySnapshotTestCase,
    GatherSourceColumnsTestCase,
    GatherWarehouseSnapshotTestCase,
)
from tests.integration.src.sqlbuild.compiler.planner._helpers.helpers import (
    RecordingDuckDbAdapter,
    _IncrementalModelSpec,
    build_deferred_locations_from_map,
    build_project_with_targets,
)

_INCREMENTAL_MODEL: _IncrementalModelSpec = _IncrementalModelSpec(
    name="fact_orders",
    schema="staging",
    cursor="event_time",
    ref_names=("raw_orders",),
)

_SELECTED_KEY: CompiledObjectKey = CompiledObjectKey(
    resource_type=CompiledResourceType.MODEL, name="fact_orders"
)

_ORDERS_KEY: CompiledObjectKey = CompiledObjectKey(
    resource_type=CompiledResourceType.MODEL, name="raw_orders"
)

_REVENUE_KEY: CompiledObjectKey = CompiledObjectKey(
    resource_type=CompiledResourceType.MODEL, name="revenue"
)


@pytest.mark.parametrize(
    "test_case",
    [
        GatherWarehouseSnapshotTestCase(
            description="gathers relations columns and fingerprints across schemas",
            setup_sql=(
                "CREATE TABLE staging.orders (id INTEGER, name VARCHAR)",
                "CREATE TABLE marts.revenue (amount DECIMAL)",
            ),
            model_locations={"orders": "staging", "revenue": "marts"},
            seed_locations={},
            fingerprints_to_write=(
                (
                    "staging",
                    Fingerprint(
                        node_type="model",
                        node_name="orders",
                        target_database=None,
                        target_schema=None,
                        target_name="orders",
                        run_id="run_001",
                        definition_hash="definition_a",
                        schema_fingerprint="schema_a",
                        definition="SELECT 1",
                        ts=datetime(2026, 1, 15, 12, 0, 0),
                    ),
                ),
            ),
            expected_relation_names=frozenset({"orders", "revenue"}),
            expected_column_table_names=frozenset({"orders", "revenue"}),
            expected_fingerprint_names=frozenset({"orders"}),
        ),
        GatherWarehouseSnapshotTestCase(
            description="gathers snapshot with seed locations included",
            setup_sql=(
                "CREATE TABLE staging.orders (id INTEGER)",
                "CREATE TABLE staging.country_codes (code VARCHAR)",
            ),
            model_locations={"orders": "staging"},
            seed_locations={"country_codes": "staging"},
            expected_relation_names=frozenset({"orders", "country_codes"}),
            expected_column_table_names=frozenset({"orders", "country_codes"}),
            expected_fingerprint_names=frozenset(),
        ),
        GatherWarehouseSnapshotTestCase(
            description="partitions mixed fingerprint node types into typed maps",
            setup_sql=(
                "CREATE TABLE staging.orders (id INTEGER)",
                "CREATE TABLE staging.country_codes (code VARCHAR)",
            ),
            model_locations={"orders": "staging"},
            seed_locations={"country_codes": "staging"},
            fingerprints_to_write=(
                (
                    "staging",
                    Fingerprint(
                        node_type="model",
                        node_name="orders",
                        target_database=None,
                        target_schema=None,
                        target_name="orders",
                        run_id="run_001",
                        definition_hash="model_definition",
                        schema_fingerprint="model_schema",
                        definition="SELECT 1",
                        ts=datetime(2026, 1, 15, 12, 0, 0),
                    ),
                ),
                (
                    "staging",
                    Fingerprint(
                        node_type="udf",
                        node_name="is_large_order",
                        target_database=None,
                        target_schema=None,
                        target_name="is_large_order",
                        run_id="run_001",
                        definition_hash="function_definition",
                        schema_fingerprint="",
                        definition="amount > 100",
                        ts=datetime(2026, 1, 15, 12, 0, 1),
                    ),
                ),
                (
                    "staging",
                    Fingerprint(
                        node_type="seed",
                        node_name="country_codes",
                        target_database=None,
                        target_schema=None,
                        target_name="country_codes",
                        run_id="run_001",
                        definition_hash="seed_definition",
                        schema_fingerprint="",
                        definition='{"columns": []}',
                        ts=datetime(2026, 1, 15, 12, 0, 2),
                    ),
                ),
            ),
            expected_relation_names=frozenset({"orders", "country_codes"}),
            expected_column_table_names=frozenset({"orders", "country_codes"}),
            expected_fingerprint_names=frozenset({"orders"}),
            expected_function_fingerprint_names=frozenset({"is_large_order"}),
            expected_seed_fingerprint_names=frozenset({"country_codes"}),
        ),
        GatherWarehouseSnapshotTestCase(
            description="filters metadata to selected model and unselected upstream names",
            setup_sql=(
                "CREATE TABLE staging.raw_orders (id INTEGER)",
                "CREATE TABLE staging.revenue (amount DECIMAL)",
                "CREATE TABLE staging.unrelated (value VARCHAR)",
            ),
            model_locations={"raw_orders": "staging", "revenue": "staging"},
            model_deps={"revenue": ("raw_orders",)},
            seed_locations={},
            selected_keys=frozenset({_REVENUE_KEY}),
            expected_relation_names=frozenset({"raw_orders", "revenue"}),
            expected_column_table_names=frozenset({"raw_orders", "revenue"}),
            expected_fingerprint_names=frozenset(),
        ),
        GatherWarehouseSnapshotTestCase(
            description="falls back to schema-wide metadata when selected scope exceeds threshold",
            setup_sql=(
                *(f"CREATE TABLE staging.model_{index} (id INTEGER)" for index in range(251)),
                "CREATE TABLE staging.unrelated (value VARCHAR)",
            ),
            model_locations={
                f"model_{index}": "staging" for index in range(METADATA_NAME_FILTER_LIMIT + 1)
            },
            seed_locations={},
            selected_keys=frozenset(
                CompiledObjectKey(resource_type=CompiledResourceType.MODEL, name=f"model_{index}")
                for index in range(METADATA_NAME_FILTER_LIMIT + 1)
            ),
            expected_relation_names=frozenset(
                {*(f"model_{index}" for index in range(251)), "unrelated"}
            ),
            expected_column_table_names=frozenset(
                {*(f"model_{index}" for index in range(251)), "unrelated"}
            ),
            expected_fingerprint_names=frozenset(),
        ),
    ],
    ids=lambda case: case.description,
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
            render_qualified_name=adapter.render_qualified_name,
            render_framework_type=adapter.render_framework_type,
        )

    project: CompiledProject = build_project_with_targets(
        model_locations=test_case.model_locations,
        model_deps=test_case.model_deps,
        seed_locations=test_case.seed_locations,
    )
    snapshot: WarehouseSnapshot = gather_warehouse_snapshot(
        project=project,
        adapter=adapter,
        connection=connection,
        execute=execute,
        selected_keys=test_case.selected_keys,
    )

    assert frozenset(snapshot.existing_relations.keys()) == test_case.expected_relation_names
    assert frozenset(snapshot.existing_columns.keys()) == test_case.expected_column_table_names
    assert frozenset(snapshot.fingerprints.models.keys()) == test_case.expected_fingerprint_names
    assert (
        frozenset(snapshot.fingerprints.functions.keys())
        == test_case.expected_function_fingerprint_names
    )
    assert (
        frozenset(snapshot.fingerprints.seeds.keys()) == test_case.expected_seed_fingerprint_names
    )


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
    ids=lambda case: case.description,
)
def test_given_no_target_schemas_when_gathering_snapshot_then_returns_empty(
    test_case: GatherEmptySnapshotTestCase,
    adapter: DuckDbAdapter,
    connection: Any,
    execute: Any,
) -> None:
    project: CompiledProject = build_project_with_targets(model_locations={}, seed_locations={})
    snapshot: WarehouseSnapshot = gather_warehouse_snapshot(
        project=project,
        adapter=adapter,
        connection=connection,
        execute=execute,
    )

    assert len(snapshot.existing_relations) == test_case.expected_relation_count
    assert len(snapshot.existing_columns) == test_case.expected_column_count
    assert len(snapshot.fingerprints.models) == test_case.expected_fingerprint_count


@pytest.mark.parametrize(
    "test_case",
    [
        GatherSourceColumnsTestCase(
            description="filters source column metadata to declared source table names",
            setup_sql=(
                "CREATE SCHEMA raw",
                "CREATE TABLE raw.orders (id INTEGER)",
                "CREATE TABLE raw.unrelated (value VARCHAR)",
            ),
            source_names=(("raw_orders", "raw", "orders"),),
            expected_source_names=frozenset({"raw_orders"}),
            expected_get_all_columns_names=(("orders",),),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_sources_when_gathering_source_columns_then_filters_metadata_names(
    test_case: GatherSourceColumnsTestCase,
    connection: Any,
) -> None:
    statement: str
    for statement in test_case.setup_sql:
        connection.execute(statement)
    adapter: RecordingDuckDbAdapter = RecordingDuckDbAdapter()
    project: CompiledProject = build_project_with_targets(source_names=test_case.source_names)

    columns: dict[str, tuple[ColumnInfo, ...]] = gather_source_columns(
        project=project,
        adapter=adapter,
        connection=connection,
    )

    assert frozenset(columns.keys()) == test_case.expected_source_names
    assert tuple(adapter.get_all_columns_names) == test_case.expected_get_all_columns_names


@pytest.mark.parametrize(
    "test_case",
    [
        GatherCursorSnapshotTestCase(
            description="gathers cursor bounds for incremental model with existing target",
            setup_sql=(
                "CREATE TABLE staging.raw_orders (order_id INTEGER, event_time TIMESTAMP)",
                "INSERT INTO staging.raw_orders VALUES (1, '2024-01-01'), (2, '2024-02-01')",
                "CREATE TABLE staging.fact_orders (order_id INTEGER, event_time TIMESTAMP)",
                "INSERT INTO staging.fact_orders VALUES (1, '2024-01-15')",
            ),
            selected_keys=frozenset({_SELECTED_KEY}),
            full_refresh=False,
            expected_cursor_model_names=frozenset({"fact_orders"}),
            expected_cursor_snapshots={
                "fact_orders": ModelCursorSnapshot(
                    target_max="2024-01-15 00:00:00",
                    upstream_mins=("2024-01-01 00:00:00",),
                    upstream_maxes=("2024-02-01 00:00:00",),
                ),
            },
            expected_progress_calls=2,
        ),
        GatherCursorSnapshotTestCase(
            description="gathers cursor bounds for first run with no target table",
            setup_sql=(
                "CREATE TABLE staging.raw_orders (order_id INTEGER, event_time TIMESTAMP)",
                "INSERT INTO staging.raw_orders VALUES (1, '2024-01-01'), (2, '2024-02-01')",
            ),
            selected_keys=frozenset({_SELECTED_KEY}),
            full_refresh=False,
            expected_cursor_model_names=frozenset({"fact_orders"}),
            expected_cursor_snapshots={
                "fact_orders": ModelCursorSnapshot(
                    target_max=None,
                    upstream_mins=("2024-01-01 00:00:00",),
                    upstream_maxes=("2024-02-01 00:00:00",),
                ),
            },
            expected_progress_calls=2,
        ),
        GatherCursorSnapshotTestCase(
            description="skips cursor gathering when full refresh is true",
            setup_sql=(
                "CREATE TABLE staging.raw_orders (order_id INTEGER, event_time TIMESTAMP)",
                "INSERT INTO staging.raw_orders VALUES (1, '2024-01-01')",
            ),
            selected_keys=frozenset({_SELECTED_KEY}),
            full_refresh=True,
            expected_cursor_model_names=frozenset(),
            expected_progress_calls=0,
        ),
        GatherCursorSnapshotTestCase(
            description="skips unselected incremental models",
            setup_sql=(
                "CREATE TABLE staging.raw_orders (order_id INTEGER, event_time TIMESTAMP)",
                "INSERT INTO staging.raw_orders VALUES (1, '2024-01-01')",
            ),
            selected_keys=frozenset(),
            full_refresh=False,
            expected_cursor_model_names=frozenset(),
            expected_progress_calls=0,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_incremental_models_when_gathering_cursor_snapshots_then_returns_expected(
    test_case: GatherCursorSnapshotTestCase,
    adapter: DuckDbAdapter,
    connection: Any,
    execute: Any,
) -> None:
    statement: str
    for statement in test_case.setup_sql:
        connection.execute(statement)

    progress_calls: list[str] = []

    def _track_progress(message: str) -> None:
        progress_calls.append(message)

    project: CompiledProject = build_project_with_targets(
        model_locations={"raw_orders": "staging"},
        incremental_models=(_INCREMENTAL_MODEL,),
    )
    snapshot: WarehouseSnapshot = gather_warehouse_snapshot(
        project=project,
        adapter=adapter,
        connection=connection,
        execute=execute,
        selected_keys=test_case.selected_keys,
        full_refresh=test_case.full_refresh,
        on_progress=_track_progress,
    )

    assert frozenset(snapshot.cursor_snapshots.keys()) == test_case.expected_cursor_model_names
    model_name: str
    expected_snap: ModelCursorSnapshot
    for model_name, expected_snap in test_case.expected_cursor_snapshots.items():
        assert snapshot.cursor_snapshots[model_name] == expected_snap
    assert len(progress_calls) == test_case.expected_progress_calls


@pytest.mark.parametrize(
    "test_case",
    [
        GatherCursorSnapshotTestCase(
            description="selected upstream reads cursor from current env not deferred",
            setup_sql=(
                "CREATE SCHEMA prod",
                "CREATE TABLE staging.raw_orders (order_id INTEGER, event_time TIMESTAMP)",
                "INSERT INTO staging.raw_orders VALUES (1, '2024-01-01'), (2, '2024-03-01')",
                "CREATE TABLE prod.raw_orders (order_id INTEGER, event_time TIMESTAMP)",
                "INSERT INTO prod.raw_orders VALUES (1, '2024-01-01'), (2, '2024-06-01')",
            ),
            selected_keys=frozenset({_SELECTED_KEY, _ORDERS_KEY}),
            full_refresh=False,
            deferred_locations={"raw_orders": "prod.raw_orders"},
            expected_cursor_model_names=frozenset({"fact_orders"}),
            expected_cursor_snapshots={
                "fact_orders": ModelCursorSnapshot(
                    target_max=None,
                    upstream_mins=("2024-01-01 00:00:00",),
                    upstream_maxes=("2024-03-01 00:00:00",),
                ),
            },
            expected_progress_calls=2,
        ),
        GatherCursorSnapshotTestCase(
            description="non-selected upstream reads cursor from deferred env",
            setup_sql=(
                "CREATE SCHEMA prod",
                "CREATE TABLE staging.raw_orders (order_id INTEGER, event_time TIMESTAMP)",
                "INSERT INTO staging.raw_orders VALUES (1, '2024-01-01'), (2, '2024-03-01')",
                "CREATE TABLE prod.raw_orders (order_id INTEGER, event_time TIMESTAMP)",
                "INSERT INTO prod.raw_orders VALUES (1, '2024-01-01'), (2, '2024-06-01')",
            ),
            selected_keys=frozenset({_SELECTED_KEY}),
            full_refresh=False,
            deferred_locations={"raw_orders": "prod.raw_orders"},
            expected_cursor_model_names=frozenset({"fact_orders"}),
            expected_cursor_snapshots={
                "fact_orders": ModelCursorSnapshot(
                    target_max=None,
                    upstream_mins=("2024-01-01 00:00:00",),
                    upstream_maxes=("2024-06-01 00:00:00",),
                ),
            },
            expected_progress_calls=2,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_deferred_locations_when_gathering_cursor_snapshots_then_resolves_correct_env(
    test_case: GatherCursorSnapshotTestCase,
    adapter: DuckDbAdapter,
    connection: Any,
    execute: Any,
) -> None:
    statement: str
    for statement in test_case.setup_sql:
        connection.execute(statement)

    progress_calls: list[str] = []

    def _track_progress(message: str) -> None:
        progress_calls.append(message)

    deferred: dict[str, CompiledRelationLocation] | None = (
        build_deferred_locations_from_map(test_case.deferred_locations)
        if test_case.deferred_locations is not None
        else None
    )

    project: CompiledProject = build_project_with_targets(
        model_locations={"raw_orders": "staging"},
        incremental_models=(_INCREMENTAL_MODEL,),
    )
    snapshot: WarehouseSnapshot = gather_warehouse_snapshot(
        project=project,
        adapter=adapter,
        connection=connection,
        execute=execute,
        selected_keys=test_case.selected_keys,
        full_refresh=test_case.full_refresh,
        on_progress=_track_progress,
        deferred_locations=deferred,
    )

    assert frozenset(snapshot.cursor_snapshots.keys()) == test_case.expected_cursor_model_names
    model_name: str
    expected_snap: ModelCursorSnapshot
    for model_name, expected_snap in test_case.expected_cursor_snapshots.items():
        assert snapshot.cursor_snapshots[model_name] == expected_snap
    assert len(progress_calls) == test_case.expected_progress_calls
