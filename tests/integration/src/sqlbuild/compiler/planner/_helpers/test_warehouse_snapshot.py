from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from typing import Any

import pytest

from sqlbuild.adapter.contract.models import ColumnInfo
from sqlbuild.adapters.duckdb.classes.duckdb_adapter import DuckDbAdapter
from sqlbuild.compiler.compile.models import (
    CompiledModel,
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
from sqlbuild.compiler.planner.exceptions import PlannerInputError
from sqlbuild.compiler.planner.models import (
    CursorOverrides,
    CursorSnapshotScope,
    ModelCursorSnapshot,
    WarehouseSnapshot,
)
from sqlbuild.spec.contracts.models import SchemaColumn, SchemaModelEntry
from tests.integration.src.sqlbuild.compiler.planner._helpers._test_types import (
    GatherCappedProducerSnapshotTestCase,
    GatherCursorSnapshotTestCase,
    GatherEmptySnapshotTestCase,
    GatherInvalidCursorScopeTestCase,
    GatherMixedGrainEligibilityTestCase,
    GatherOverrideCursorSnapshotTestCase,
    GatherSelectedCursorScopeTestCase,
    GatherSharedCursorSnapshotTestCase,
    GatherSourceColumnsTestCase,
    GatherWarehouseSnapshotTestCase,
    GatherWatermarkTypeTestCase,
)
from tests.integration.src.sqlbuild.compiler.planner._helpers.helpers import (
    RecordingDuckDbAdapter,
    _FailEligibleCursorAdapter,
    _IncrementalModelSpec,
    build_deferred_locations_from_map,
    build_project_with_targets,
    with_leading_enforced_model_contracts,
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
    (
        GatherCappedProducerSnapshotTestCase(
            description="capped producer uses physical availability",
            expected_availability_ends=("2025-10-15T00:00:00",),
            expected_availability_ranges=(("2025-08-15 00:00:00", "2025-10-15T00:00:00"),),
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_unselected_capped_terminal_producer_when_gathering_then_physical_range_is_authoritative(
    adapter: DuckDbAdapter,
    connection: Any,
    execute: Any,
    test_case: GatherCappedProducerSnapshotTestCase,
) -> None:
    connection.execute("CREATE TABLE staging.capped_events (event_time TIMESTAMP)")
    connection.execute("INSERT INTO staging.capped_events VALUES ('2025-08-15'), ('2025-09-15')")
    connection.execute("CREATE TABLE staging.downstream_events (event_time TIMESTAMP)")
    connection.execute("INSERT INTO staging.downstream_events VALUES ('2025-01-01')")
    project: CompiledProject = build_project_with_targets(
        incremental_models=(
            _IncrementalModelSpec(
                name="capped_events",
                schema="staging",
                cursor="event_time",
                ref_names=(),
                extra_config={
                    "cursor_type": "timestamp",
                    "cursor_grain": "month",
                    "incremental_mode": "microbatch",
                    "microbatch_strategy": "watermark",
                    "cursor_start": "2025-01-01",
                    "cursor_end": "2025-12-01",
                    "microbatch_limit": {
                        "max_batches": 2,
                        "action": "cap_from_end",
                    },
                },
            ),
            _IncrementalModelSpec(
                name="downstream_events",
                schema="staging",
                cursor="event_time",
                ref_names=("capped_events",),
                extra_config={
                    "cursor_type": "timestamp",
                    "cursor_grain": "month",
                    "incremental_mode": "microbatch",
                    "microbatch_strategy": "watermark",
                    "cursor_watermark_mode": "all",
                    "cursor_inputs": {
                        "capped_events": {
                            "column": "event_time",
                            "roles": ["filter", "watermark"],
                        }
                    },
                },
            ),
        )
    )
    downstream_key: CompiledObjectKey = CompiledObjectKey(
        resource_type=CompiledResourceType.MODEL,
        name="downstream_events",
    )

    snapshot: WarehouseSnapshot = gather_warehouse_snapshot(
        project=project,
        adapter=adapter,
        connection=connection,
        execute=execute,
        selected_keys=frozenset(model.key for model in project.models),
        cursor_scope=CursorSnapshotScope(
            model_keys=frozenset({downstream_key}),
            runtime_producer_keys=frozenset({downstream_key}),
        ),
    )

    cursor_snapshot: ModelCursorSnapshot = snapshot.cursor_snapshots["downstream_events"]
    assert cursor_snapshot.upstream_terminal_starts == ()
    assert cursor_snapshot.upstream_terminal_ends == ()
    assert cursor_snapshot.upstream_availability_ends == test_case.expected_availability_ends
    assert cursor_snapshot.upstream_availability_ranges == test_case.expected_availability_ranges


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
            description="filters metadata to selected model transitive upstream closure",
            setup_sql=(
                "CREATE TABLE staging.raw_orders (id INTEGER)",
                "CREATE TABLE marts.stg_orders (id INTEGER)",
                "CREATE TABLE marts.revenue (amount DECIMAL)",
                "CREATE TABLE staging.unrelated (value VARCHAR)",
            ),
            model_locations={
                "raw_orders": "staging",
                "stg_orders": "marts",
                "revenue": "marts",
            },
            model_deps={"stg_orders": ("raw_orders",), "revenue": ("stg_orders",)},
            seed_locations={},
            selected_keys=frozenset({_REVENUE_KEY}),
            expected_relation_names=frozenset({"raw_orders", "stg_orders", "revenue"}),
            expected_column_table_names=frozenset({"raw_orders", "stg_orders", "revenue"}),
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
            expected_progress_calls=5,
        ),
        GatherCursorSnapshotTestCase(
            description="derives highest eligible target max without removing future rows",
            setup_sql=(
                "CREATE TABLE staging.raw_orders (order_id INTEGER, event_time TIMESTAMP)",
                "INSERT INTO staging.raw_orders VALUES (1, '2024-01-01'), (2, '2024-02-01')",
                "CREATE TABLE staging.fact_orders (order_id INTEGER, event_time TIMESTAMP)",
                "INSERT INTO staging.fact_orders VALUES (1, '2024-01-15'), (2, '2024-02-01')",
            ),
            selected_keys=frozenset({_SELECTED_KEY}),
            full_refresh=False,
            model_extra_config={
                "cursor_type": "timestamp",
                "cursor_grain": "day",
                "cursor_start_max_ahead": "0d",
                "cursor_start_max_action": "cap",
            },
            cursor_scope=CursorSnapshotScope(
                model_keys=frozenset({_SELECTED_KEY}),
                runtime_producer_keys=frozenset({_SELECTED_KEY}),
                invocation_time=datetime(2024, 1, 20, 12, tzinfo=UTC),
            ),
            expected_cursor_model_names=frozenset({"fact_orders"}),
            expected_cursor_snapshots={
                "fact_orders": ModelCursorSnapshot(
                    target_max="2024-02-01 00:00:00",
                    target_eligible_max="2024-01-15T00:00:00",
                    upstream_mins=("2024-01-01 00:00:00",),
                    upstream_maxes=("2024-02-01 00:00:00",),
                ),
            },
            expected_progress_calls=5,
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
            expected_progress_calls=3,
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
            description="gathers cursor bounds when model opts out of full refresh",
            setup_sql=(
                "CREATE TABLE staging.raw_orders (order_id INTEGER, event_time TIMESTAMP)",
                "INSERT INTO staging.raw_orders VALUES (1, '2024-02-01')",
            ),
            selected_keys=frozenset({_SELECTED_KEY}),
            full_refresh=True,
            expected_cursor_model_names=frozenset({"fact_orders"}),
            model_extra_config={"full_refresh": False},
            expected_cursor_snapshots={
                "fact_orders": ModelCursorSnapshot(
                    target_max=None,
                    upstream_mins=("2024-02-01 00:00:00",),
                    upstream_maxes=("2024-02-01 00:00:00",),
                ),
            },
            expected_progress_calls=3,
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
        incremental_models=(
            _IncrementalModelSpec(
                name=_INCREMENTAL_MODEL.name,
                schema=_INCREMENTAL_MODEL.schema,
                cursor=_INCREMENTAL_MODEL.cursor,
                ref_names=_INCREMENTAL_MODEL.ref_names,
                extra_config=test_case.model_extra_config,
            ),
        ),
    )
    snapshot: WarehouseSnapshot = gather_warehouse_snapshot(
        project=project,
        adapter=adapter,
        connection=connection,
        execute=execute,
        selected_keys=test_case.selected_keys,
        full_refresh=test_case.full_refresh,
        on_progress=_track_progress,
        cursor_scope=test_case.cursor_scope,
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
            deferred_locations=build_deferred_locations_from_map({"raw_orders": "prod.raw_orders"}),
            expected_cursor_model_names=frozenset({"fact_orders"}),
            expected_cursor_snapshots={
                "fact_orders": ModelCursorSnapshot(
                    target_max=None,
                    upstream_mins=(),
                    upstream_maxes=(),
                ),
            },
            expected_progress_calls=1,
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
            deferred_locations=build_deferred_locations_from_map({"raw_orders": "prod.raw_orders"}),
            expected_cursor_model_names=frozenset({"fact_orders"}),
            expected_cursor_snapshots={
                "fact_orders": ModelCursorSnapshot(
                    target_max=None,
                    upstream_mins=("2024-01-01 00:00:00",),
                    upstream_maxes=("2024-06-01 00:00:00",),
                ),
            },
            expected_progress_calls=3,
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

    deferred: dict[str, CompiledRelationLocation] | None = test_case.deferred_locations

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


@pytest.mark.parametrize(
    "test_case",
    [
        GatherSharedCursorSnapshotTestCase(
            description="two models share one physical source cursor read",
            expected_cursor_snapshot=ModelCursorSnapshot(
                target_max=None,
                upstream_mins=("2024-01-01 00:00:00",),
                upstream_maxes=("2024-03-01 00:00:00",),
            ),
            expected_statements=(
                "SELECT CAST(MIN(event_time) AS VARCHAR) AS _min, "
                "CAST(MAX(event_time) AS VARCHAR) AS _max FROM staging.raw_events",
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_models_sharing_one_source_when_gathering_snapshot_then_executes_one_bounds_statement(
    test_case: GatherSharedCursorSnapshotTestCase,
    adapter: DuckDbAdapter,
    connection: Any,
) -> None:
    connection.execute("CREATE TABLE staging.raw_events (event_time TIMESTAMP)")
    connection.execute("INSERT INTO staging.raw_events VALUES ('2024-01-01'), ('2024-03-01')")
    statements: list[str] = []

    def _record_execute(*, connection: Any, sql: str) -> Any:
        statements.append(sql)
        return connection.execute(sql)

    project: CompiledProject = build_project_with_targets(
        model_locations={"raw_events": "staging"},
        incremental_models=(
            _IncrementalModelSpec(
                name="daily_events",
                schema="staging",
                cursor="event_time",
                ref_names=("raw_events",),
            ),
            _IncrementalModelSpec(
                name="monthly_events",
                schema="staging",
                cursor="event_time",
                ref_names=("raw_events",),
            ),
        ),
    )

    snapshot: WarehouseSnapshot = gather_warehouse_snapshot(
        project=project,
        adapter=adapter,
        connection=connection,
        execute=_record_execute,
    )

    assert snapshot.cursor_snapshots == {
        "daily_events": test_case.expected_cursor_snapshot,
        "monthly_events": test_case.expected_cursor_snapshot,
    }
    assert tuple(statements) == test_case.expected_statements


@pytest.mark.parametrize(
    "test_case",
    [
        GatherOverrideCursorSnapshotTestCase(
            description="explicit timestamp start skips eligible target query",
            expected_target_max="2026-09-03 00:00:00",
            expected_eligible_max=None,
            expected_statement_count=2,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_explicit_start_when_gathering_snapshot_then_eligible_query_is_never_attempted(
    test_case: GatherOverrideCursorSnapshotTestCase,
    adapter: DuckDbAdapter,
    connection: Any,
) -> None:
    connection.execute("CREATE TABLE staging.raw_events (event_time TIMESTAMP)")
    connection.execute("INSERT INTO staging.raw_events VALUES ('2026-08-01'), ('2026-09-03')")
    connection.execute("CREATE TABLE staging.daily_events (event_time TIMESTAMP)")
    connection.execute("INSERT INTO staging.daily_events VALUES ('2026-09-03')")
    statements: list[str] = []

    def _fail_eligible_execute(*, connection: Any, sql: str) -> Any:
        statements.append(sql)
        return connection.execute(sql)

    project: CompiledProject = build_project_with_targets(
        model_locations={"raw_events": "staging"},
        incremental_models=(
            _IncrementalModelSpec(
                name="daily_events",
                schema="staging",
                cursor="event_time",
                ref_names=("raw_events",),
                extra_config={
                    "cursor_type": "timestamp",
                    "cursor_grain": "day",
                    "cursor_start_max_ahead": "0d",
                    "cursor_start_max_action": "cap",
                },
            ),
        ),
    )
    daily_events_key: CompiledObjectKey = CompiledObjectKey(
        resource_type=CompiledResourceType.MODEL, name="daily_events"
    )

    snapshot: WarehouseSnapshot = gather_warehouse_snapshot(
        project=project,
        adapter=_FailEligibleCursorAdapter(),
        connection=connection,
        execute=_fail_eligible_execute,
        cursor_scope=CursorSnapshotScope(
            model_keys=frozenset({daily_events_key}),
            runtime_producer_keys=frozenset({daily_events_key}),
            invocation_time=datetime(2026, 9, 1, 12, tzinfo=UTC),
            cursor_overrides=CursorOverrides(start_ts="2026-07-01"),
        ),
    )

    cursor_snapshot: ModelCursorSnapshot = snapshot.cursor_snapshots["daily_events"]
    assert cursor_snapshot.target_max == test_case.expected_target_max
    assert cursor_snapshot.target_eligible_max == test_case.expected_eligible_max
    assert len(statements) == test_case.expected_statement_count


@pytest.mark.parametrize(
    "test_case",
    [
        GatherMixedGrainEligibilityTestCase(
            description="planner eligible query and result use common day grain",
            expected_eligible_max="2024-01-15T00:00:00",
            expected_eligible_sql=(
                'SELECT MAX("event_time") FROM staging.hourly_events '
                "WHERE \"event_time\" <= TIMESTAMP '2024-01-20T00:00:00'"
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_mixed_model_grains_when_gathering_eligibility_then_warehouse_flow_matches_runtime(
    test_case: GatherMixedGrainEligibilityTestCase,
    adapter: DuckDbAdapter,
    connection: Any,
) -> None:
    connection.execute("CREATE TABLE staging.daily_events (event_time TIMESTAMP)")
    connection.execute("INSERT INTO staging.daily_events VALUES ('2024-01-01'), ('2024-02-01')")
    connection.execute("CREATE TABLE staging.hourly_events (event_time TIMESTAMP)")
    connection.execute(
        "INSERT INTO staging.hourly_events VALUES ('2024-01-15 18:00:00'), ('2024-02-01 15:00:00')"
    )
    statements: list[str] = []

    def _record_execute(*, connection: Any, sql: str) -> Any:
        statements.append(sql)
        return connection.execute(sql)

    project: CompiledProject = build_project_with_targets(
        incremental_models=(
            _IncrementalModelSpec(
                name="daily_events",
                schema="staging",
                cursor="event_time",
                ref_names=(),
                extra_config={"cursor_type": "timestamp", "cursor_grain": "day"},
            ),
            _IncrementalModelSpec(
                name="hourly_events",
                schema="staging",
                cursor="event_time",
                ref_names=("daily_events",),
                extra_config={
                    "cursor_type": "timestamp",
                    "cursor_grain": "hour",
                    "cursor_start_max_ahead": "0d",
                    "cursor_start_max_action": "cap",
                },
            ),
        ),
    )
    hourly_key: CompiledObjectKey = CompiledObjectKey(
        resource_type=CompiledResourceType.MODEL, name="hourly_events"
    )

    snapshot: WarehouseSnapshot = gather_warehouse_snapshot(
        project=project,
        adapter=adapter,
        connection=connection,
        execute=_record_execute,
        cursor_scope=CursorSnapshotScope(
            model_keys=frozenset({hourly_key}),
            runtime_producer_keys=frozenset({hourly_key}),
            invocation_time=datetime(2024, 1, 20, 12, tzinfo=UTC),
        ),
    )

    cursor_snapshot: ModelCursorSnapshot = snapshot.cursor_snapshots["hourly_events"]
    assert cursor_snapshot.target_eligible_max == test_case.expected_eligible_max
    assert test_case.expected_eligible_sql in statements
    assert "UNION ALL" not in statements[0]


@pytest.mark.parametrize(
    "test_case",
    [
        GatherSelectedCursorScopeTestCase(
            description="selected cursor ignores unrelated invalid model",
            expected_cursor_snapshot=ModelCursorSnapshot(
                target_max=None,
                upstream_mins=("2024-01-01 00:00:00",),
                upstream_maxes=("2024-03-01 00:00:00",),
            ),
            expected_statements=(
                "SELECT CAST(MIN(event_time) AS VARCHAR) AS _min, "
                "CAST(MAX(event_time) AS VARCHAR) AS _max FROM staging.valid_upstream",
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_broad_metadata_scope_when_gathering_selected_cursor_then_ignores_unrelated_invalid_model(
    test_case: GatherSelectedCursorScopeTestCase,
    adapter: DuckDbAdapter,
    connection: Any,
) -> None:
    connection.execute("CREATE TABLE staging.valid_upstream (event_time TIMESTAMP)")
    connection.execute("INSERT INTO staging.valid_upstream VALUES ('2024-01-01'), ('2024-03-01')")
    connection.execute("CREATE TABLE staging.invalid_upstream (id INTEGER)")
    statements: list[str] = []

    def _record_execute(*, connection: Any, sql: str) -> Any:
        statements.append(sql)
        return connection.execute(sql)

    project: CompiledProject = build_project_with_targets(
        model_locations={"valid_upstream": "staging", "invalid_upstream": "staging"},
        incremental_models=(
            _IncrementalModelSpec(
                name="selected_cursor",
                schema="staging",
                cursor="event_time",
                ref_names=("valid_upstream",),
            ),
            _IncrementalModelSpec(
                name="unrelated_cursor",
                schema="staging",
                cursor="event_time",
                ref_names=("invalid_upstream",),
                extra_config={
                    "microbatch_strategy": "watermark",
                    "cursor_watermark_mode": "all",
                    "cursor_inputs": {
                        "invalid_upstream": {
                            "column": "meeting_date",
                            "roles": ["watermark"],
                        }
                    },
                },
            ),
        ),
    )
    project = with_leading_enforced_model_contracts(
        project,
        columns_by_model={
            "valid_upstream": ("event_time",),
            "invalid_upstream": ("id",),
        },
    )
    selected_cursor_key: CompiledObjectKey = CompiledObjectKey(
        resource_type=CompiledResourceType.MODEL,
        name="selected_cursor",
    )
    metadata_keys: frozenset[CompiledObjectKey] = frozenset(model.key for model in project.models)

    snapshot: WarehouseSnapshot = gather_warehouse_snapshot(
        project=project,
        adapter=adapter,
        connection=connection,
        execute=_record_execute,
        selected_keys=metadata_keys,
        cursor_scope=CursorSnapshotScope(
            model_keys=frozenset({selected_cursor_key}),
            runtime_producer_keys=frozenset({selected_cursor_key}),
        ),
    )

    assert snapshot.cursor_snapshots == {"selected_cursor": test_case.expected_cursor_snapshot}
    assert tuple(statements) == test_case.expected_statements


@pytest.mark.parametrize(
    "test_case",
    [
        GatherInvalidCursorScopeTestCase(
            description="selected invalid cursor fails precise contract validation",
            expected_error_code="S302",
            expected_error_fragment="Declared contract columns: id",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_selected_invalid_cursor_model_when_gathering_snapshot_then_raises_s302(
    test_case: GatherInvalidCursorScopeTestCase,
    adapter: DuckDbAdapter,
    connection: Any,
    execute: Any,
) -> None:
    connection.execute("CREATE TABLE staging.invalid_upstream (id INTEGER)")
    project: CompiledProject = build_project_with_targets(
        model_locations={"invalid_upstream": "staging"},
        incremental_models=(
            _IncrementalModelSpec(
                name="invalid_cursor",
                schema="staging",
                cursor="id",
                ref_names=("invalid_upstream",),
                extra_config={
                    "microbatch_strategy": "watermark",
                    "cursor_watermark_mode": "all",
                    "cursor_inputs": {
                        "invalid_upstream": {
                            "column": "meeting_date",
                            "roles": ["watermark"],
                        }
                    },
                },
            ),
        ),
    )
    project = with_leading_enforced_model_contracts(
        project,
        columns_by_model={"invalid_upstream": ("id",)},
    )
    invalid_cursor_key: CompiledObjectKey = CompiledObjectKey(
        resource_type=CompiledResourceType.MODEL,
        name="invalid_cursor",
    )

    with pytest.raises(PlannerInputError, match=test_case.expected_error_fragment) as exc_info:
        gather_warehouse_snapshot(
            project=project,
            adapter=adapter,
            connection=connection,
            execute=execute,
            selected_keys=frozenset(model.key for model in project.models),
            cursor_scope=CursorSnapshotScope(
                model_keys=frozenset({invalid_cursor_key}),
                runtime_producer_keys=frozenset({invalid_cursor_key}),
            ),
        )

    assert exc_info.value.code == test_case.expected_error_code


@pytest.mark.parametrize(
    "test_case",
    (
        GatherWatermarkTypeTestCase(
            description="full refresh rejects time-only watermark",
            declared_type="TIME",
            expected_error_fragment="type TIME is incompatible",
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_full_refresh_with_time_only_watermark_contract_when_gathering_then_type_validation_runs(
    test_case: GatherWatermarkTypeTestCase,
    adapter: DuckDbAdapter,
    connection: Any,
    execute: Any,
) -> None:
    project: CompiledProject = build_project_with_targets(
        model_locations={"upstream_events": "staging"},
        incremental_models=(
            _IncrementalModelSpec(
                name="daily_events",
                schema="staging",
                cursor="event_time",
                ref_names=("upstream_events",),
                extra_config={
                    "incremental_mode": "microbatch",
                    "microbatch_strategy": "watermark",
                    "cursor_watermark_mode": "all",
                    "cursor_type": "timestamp",
                    "cursor_grain": "day",
                    "cursor_inputs": {
                        "upstream_events": {
                            "column": "event_time",
                            "roles": ["watermark"],
                        }
                    },
                },
            ),
        ),
    )
    upstream: CompiledModel = replace(
        project.models[0],
        config=replace(
            project.models[0].config,
            values=project.models[0].config.values | {"contract": "enforced"},
        ),
        schema_entry=SchemaModelEntry(
            name="upstream_events",
            columns=(SchemaColumn(name="event_time", type=test_case.declared_type),),
        ),
    )
    project = replace(project, models=(upstream, project.models[1]))
    daily_key: CompiledObjectKey = project.models[1].key

    with pytest.raises(PlannerInputError, match=test_case.expected_error_fragment):
        gather_warehouse_snapshot(
            project=project,
            adapter=adapter,
            connection=connection,
            execute=execute,
            selected_keys=frozenset(model.key for model in project.models),
            full_refresh_model_names=frozenset({"daily_events"}),
            cursor_scope=CursorSnapshotScope(
                model_keys=frozenset({daily_key}),
                runtime_producer_keys=frozenset({daily_key}),
            ),
        )


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
