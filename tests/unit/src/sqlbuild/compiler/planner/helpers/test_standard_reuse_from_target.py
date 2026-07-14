from __future__ import annotations

from dataclasses import replace

import pytest

from sqlbuild.compiler.compile.models.core import (
    CompiledModel,
    CompiledProject,
    CompiledRelationLocation,
)
from sqlbuild.compiler.planner.exceptions import PlannerInputError
from sqlbuild.compiler.planner.helpers.reuse.standard_reuse_from_target import (
    build_standard_reuse_from_target_snapshot,
)
from sqlbuild.compiler.planner.models import PlannerScope, StandardReuseFromTargetSnapshot
from sqlbuild.spec.contracts.models import LocalConfig, ProjectConfig, TargetConfig
from tests.unit.src.sqlbuild.compiler.planner.helpers._test_types import (
    StandardReuseFromTargetMultiSchemaTestCase,
    StandardReuseFromTargetNoConfigTestCase,
    StandardReuseFromTargetSnapshotErrorTestCase,
    StandardReuseFromTargetSnapshotTestCase,
)
from tests.unit.src.sqlbuild.compiler.planner.helpers.helpers import (
    StandardReuseFromTargetTestAdapter,
    build_standard_reuse_from_target_fingerprint_row,
    build_standard_reuse_from_target_project,
    build_standard_reuse_from_target_scope,
)


@pytest.mark.parametrize(
    "test_case",
    [
        StandardReuseFromTargetSnapshotTestCase(
            description="reads reuse_from fingerprints and relation existence",
            fingerprint_rows=(
                build_standard_reuse_from_target_fingerprint_row(
                    model_name="orders",
                    version_hash="orders_version_hash",
                ),
            ),
            existing_relations=frozenset({(None, "prod_schema", "orders")}),
            expected_target_name="prod",
            expected_model_relation_exists={
                "account_snapshot": False,
                "orders": True,
                "customers": False,
                "line_items": False,
            },
            expected_model_built_version_hashes={
                "account_snapshot": None,
                "orders": "orders_version_hash",
                "customers": None,
                "line_items": None,
            },
            expected_model_fingerprint_schemas={
                "account_snapshot": "prod_schema",
                "orders": "prod_schema",
                "customers": "prod_schema",
                "line_items": "prod_schema",
            },
            expected_model_fingerprint_databases={
                "account_snapshot": None,
                "orders": None,
                "customers": None,
                "line_items": None,
            },
        )
    ],
    ids=lambda case: case.description,
)
def test_given_reuse_from_target_when_building_snapshot_then_reads_fingerprints_and_relations(
    test_case: StandardReuseFromTargetSnapshotTestCase,
) -> None:
    project: CompiledProject = build_standard_reuse_from_target_project()
    scope: PlannerScope = build_standard_reuse_from_target_scope()
    adapter: StandardReuseFromTargetTestAdapter = StandardReuseFromTargetTestAdapter(
        fingerprint_rows=test_case.fingerprint_rows,
        existing_relations=test_case.existing_relations,
    )

    snapshot: StandardReuseFromTargetSnapshot | None = build_standard_reuse_from_target_snapshot(
        project=project,
        adapter=adapter,
        connection=object(),
        scope=scope,
        project_config=ProjectConfig(
            name="demo",
            adapter="duckdb",
            targets={
                "dev": TargetConfig(schema="dev_schema", reuse_from="prod"),
                "prod": TargetConfig(schema="prod_schema"),
            },
        ),
        local_config=LocalConfig(),
    )

    assert snapshot is not None
    assert snapshot.reuse_from_target_name == test_case.expected_target_name
    assert {
        model_name: model_snapshot.relation_exists
        for model_name, model_snapshot in snapshot.model_snapshots.items()
    } == test_case.expected_model_relation_exists
    assert {
        model_name: model_snapshot.built_version_hash
        for model_name, model_snapshot in snapshot.model_snapshots.items()
    } == test_case.expected_model_built_version_hashes
    assert {
        model_name: model_snapshot.reuse_origin_fingerprint_schema
        for model_name, model_snapshot in snapshot.model_snapshots.items()
    } == test_case.expected_model_fingerprint_schemas
    assert {
        model_name: model_snapshot.reuse_origin_fingerprint_database
        for model_name, model_snapshot in snapshot.model_snapshots.items()
    } == test_case.expected_model_fingerprint_databases


@pytest.mark.parametrize(
    "test_case",
    [
        StandardReuseFromTargetSnapshotErrorTestCase(
            description="raises when reuse_from fingerprint table is missing",
            fingerprint_table_exists=False,
            expected_error_fragment=(
                "cannot read fingerprint state for reuse origin schema 'prod_schema'"
            ),
        ),
        StandardReuseFromTargetSnapshotErrorTestCase(
            description="raises when reuse_from fingerprint rows cannot be read",
            fingerprint_table_exists=True,
            fingerprint_read_fails=True,
            expected_error_fragment=(
                "cannot read fingerprint state for reuse origin schema 'prod_schema'"
            ),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_missing_reuse_origin_fingerprint_state_when_building_snapshot_then_it_raises(
    test_case: StandardReuseFromTargetSnapshotErrorTestCase,
) -> None:
    adapter: StandardReuseFromTargetTestAdapter = StandardReuseFromTargetTestAdapter(
        fingerprint_rows=(),
        existing_relations=frozenset(),
        fingerprint_table_exists=test_case.fingerprint_table_exists,
        fingerprint_read_fails=test_case.fingerprint_read_fails,
    )

    with pytest.raises(PlannerInputError, match=test_case.expected_error_fragment):
        build_standard_reuse_from_target_snapshot(
            project=build_standard_reuse_from_target_project(),
            adapter=adapter,
            connection=object(),
            scope=build_standard_reuse_from_target_scope(),
            project_config=ProjectConfig(
                name="demo",
                adapter="duckdb",
                targets={
                    "dev": TargetConfig(schema="dev_schema", reuse_from="prod"),
                    "prod": TargetConfig(schema="prod_schema"),
                },
            ),
            local_config=LocalConfig(),
        )


@pytest.mark.parametrize(
    "test_case",
    [
        StandardReuseFromTargetSnapshotTestCase(
            description="resolves templated reuse_from target namespace",
            fingerprint_rows=(
                build_standard_reuse_from_target_fingerprint_row(
                    model_name="orders",
                    version_hash="orders_version_hash",
                ),
            ),
            existing_relations=frozenset({("warehouse", "prod_analytics", "orders")}),
            expected_target_name="prod",
            expected_model_relation_exists={
                "account_snapshot": False,
                "orders": True,
                "customers": False,
                "line_items": False,
            },
            expected_model_built_version_hashes={
                "account_snapshot": None,
                "orders": "orders_version_hash",
                "customers": None,
                "line_items": None,
            },
            expected_model_fingerprint_schemas={
                "account_snapshot": "prod_analytics",
                "orders": "prod_analytics",
                "customers": "prod_analytics",
                "line_items": "prod_analytics",
            },
            expected_model_fingerprint_databases={
                "account_snapshot": "warehouse",
                "orders": "warehouse",
                "customers": "warehouse",
                "line_items": "warehouse",
            },
        )
    ],
    ids=lambda case: case.description,
)
def test_given_templated_reuse_from_target_when_building_snapshot_then_resolves_namespace(
    test_case: StandardReuseFromTargetSnapshotTestCase,
) -> None:
    adapter: StandardReuseFromTargetTestAdapter = StandardReuseFromTargetTestAdapter(
        fingerprint_rows=test_case.fingerprint_rows,
        existing_relations=test_case.existing_relations,
    )

    snapshot: StandardReuseFromTargetSnapshot | None = build_standard_reuse_from_target_snapshot(
        project=build_standard_reuse_from_target_project(),
        adapter=adapter,
        connection=object(),
        scope=build_standard_reuse_from_target_scope(),
        project_config=ProjectConfig(
            name="demo",
            adapter="duckdb",
            targets={
                "dev": TargetConfig(schema="dev_schema", reuse_from="prod"),
                "prod": TargetConfig(
                    database="${db}",
                    schema="${schema_prefix}_${CTX:model.schema}",
                    vars={"db": "warehouse", "schema_prefix": "prod"},
                ),
            },
        ),
        local_config=LocalConfig(),
    )

    assert snapshot is not None
    assert {
        model_name: model_snapshot.relation_exists
        for model_name, model_snapshot in snapshot.model_snapshots.items()
    } == test_case.expected_model_relation_exists
    assert {
        model_name: model_snapshot.reuse_origin_fingerprint_schema
        for model_name, model_snapshot in snapshot.model_snapshots.items()
    } == test_case.expected_model_fingerprint_schemas
    assert {
        model_name: model_snapshot.reuse_origin_fingerprint_database
        for model_name, model_snapshot in snapshot.model_snapshots.items()
    } == test_case.expected_model_fingerprint_databases


@pytest.mark.parametrize(
    "test_case",
    [
        StandardReuseFromTargetSnapshotErrorTestCase(
            description="raises when reuse_from target uses shorthand schema CTX",
            fingerprint_table_exists=True,
            expected_error_fragment=(
                r"unsupported context key '\${CTX:schema}'. Use '\${CTX:model.database}' "
                r"or '\${CTX:model.schema}' instead"
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_shorthand_ctx_in_reuse_from_target_when_building_snapshot_then_it_raises(
    test_case: StandardReuseFromTargetSnapshotErrorTestCase,
) -> None:
    adapter: StandardReuseFromTargetTestAdapter = StandardReuseFromTargetTestAdapter(
        fingerprint_rows=(),
        existing_relations=frozenset(),
        fingerprint_table_exists=test_case.fingerprint_table_exists,
    )

    with pytest.raises(PlannerInputError, match=test_case.expected_error_fragment):
        build_standard_reuse_from_target_snapshot(
            project=build_standard_reuse_from_target_project(),
            adapter=adapter,
            connection=object(),
            scope=build_standard_reuse_from_target_scope(),
            project_config=ProjectConfig(
                name="demo",
                adapter="duckdb",
                targets={
                    "dev": TargetConfig(schema="dev_schema", reuse_from="prod"),
                    "prod": TargetConfig(schema="prod_${CTX:schema}"),
                },
            ),
            local_config=LocalConfig(),
        )


@pytest.mark.parametrize(
    "test_case",
    [
        StandardReuseFromTargetMultiSchemaTestCase(
            description="tracks per-model origin fingerprint schemas",
            expected_origin_schemas={
                "orders": "prod_analytics",
                "customers": "prod_intermediate",
            },
            expected_origin_fingerprint_schemas={
                "orders": "prod_analytics",
                "customers": "prod_intermediate",
            },
            expected_origin_fingerprint_databases={"orders": None, "customers": None},
        )
    ],
    ids=lambda case: case.description,
)
def test_given_multi_schema_reuse_from_when_building_snapshot_then_tracks_origin_state(
    test_case: StandardReuseFromTargetMultiSchemaTestCase,
) -> None:
    base_project: CompiledProject = build_standard_reuse_from_target_project()
    orders_model: CompiledModel = base_project.models[0]
    customers_model: CompiledModel = replace(
        base_project.models[1],
        destination=CompiledRelationLocation(
            database=None,
            schema="dev_intermediate",
            name="customers",
            qualified_name="dev_intermediate.customers",
            logical_schema="intermediate",
        ),
    )
    project: CompiledProject = replace(base_project, models=(orders_model, customers_model))
    scope: PlannerScope = build_standard_reuse_from_target_scope(
        selected_model_names=frozenset({"orders", "customers"})
    )
    scope = replace(
        scope,
        models_by_name={model.name: model for model in project.models},
        selected_keys=frozenset(model.key for model in project.models),
        execution_order=tuple(model.key for model in project.models),
    )
    adapter: StandardReuseFromTargetTestAdapter = StandardReuseFromTargetTestAdapter(
        fingerprint_rows=(
            build_standard_reuse_from_target_fingerprint_row(
                model_name="orders",
                version_hash="orders_version_hash",
            ),
            build_standard_reuse_from_target_fingerprint_row(
                model_name="customers",
                version_hash="customers_version_hash",
            ),
        ),
        existing_relations=frozenset(
            {
                (None, "prod_analytics", "orders"),
                (None, "prod_intermediate", "customers"),
            }
        ),
    )

    snapshot: StandardReuseFromTargetSnapshot | None = build_standard_reuse_from_target_snapshot(
        project=project,
        adapter=adapter,
        connection=object(),
        scope=scope,
        project_config=ProjectConfig(
            name="demo",
            adapter="duckdb",
            targets={
                "dev": TargetConfig(schema="dev_schema", reuse_from="prod"),
                "prod": TargetConfig(schema="prod_${CTX:model.schema}"),
            },
        ),
        local_config=LocalConfig(),
    )

    assert snapshot is not None
    assert {
        model_name: model_snapshot.reuse_origin.schema
        for model_name, model_snapshot in snapshot.model_snapshots.items()
    } == test_case.expected_origin_schemas
    assert {
        model_name: model_snapshot.reuse_origin_fingerprint_schema
        for model_name, model_snapshot in snapshot.model_snapshots.items()
    } == test_case.expected_origin_fingerprint_schemas
    assert {
        model_name: model_snapshot.reuse_origin_fingerprint_database
        for model_name, model_snapshot in snapshot.model_snapshots.items()
    } == test_case.expected_origin_fingerprint_databases


@pytest.mark.parametrize(
    "test_case",
    [
        StandardReuseFromTargetSnapshotTestCase(
            description="includes only selected models",
            fingerprint_rows=(
                build_standard_reuse_from_target_fingerprint_row(
                    model_name="orders",
                    version_hash="orders_version_hash",
                ),
            ),
            existing_relations=frozenset({(None, "prod_schema", "orders")}),
            expected_target_name="prod",
            expected_model_relation_exists={"orders": True},
            expected_model_built_version_hashes={"orders": "orders_version_hash"},
            expected_model_fingerprint_schemas={"orders": "prod_schema"},
            expected_model_fingerprint_databases={"orders": None},
            expected_model_names=("orders",),
            selected_model_names=frozenset({"orders"}),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_scoped_plan_when_building_snapshot_then_includes_only_selected_models(
    test_case: StandardReuseFromTargetSnapshotTestCase,
) -> None:
    adapter: StandardReuseFromTargetTestAdapter = StandardReuseFromTargetTestAdapter(
        fingerprint_rows=test_case.fingerprint_rows,
        existing_relations=test_case.existing_relations,
    )

    snapshot: StandardReuseFromTargetSnapshot | None = build_standard_reuse_from_target_snapshot(
        project=build_standard_reuse_from_target_project(),
        adapter=adapter,
        connection=object(),
        scope=build_standard_reuse_from_target_scope(
            selected_model_names=test_case.selected_model_names
        ),
        project_config=ProjectConfig(
            name="demo",
            adapter="duckdb",
            targets={
                "dev": TargetConfig(schema="dev_schema", reuse_from="prod"),
                "prod": TargetConfig(schema="prod_schema"),
            },
        ),
        local_config=LocalConfig(),
    )

    assert snapshot is not None
    assert tuple(sorted(snapshot.model_snapshots)) == test_case.expected_model_names
    assert {
        model_name: model_snapshot.relation_exists
        for model_name, model_snapshot in snapshot.model_snapshots.items()
    } == test_case.expected_model_relation_exists


@pytest.mark.parametrize(
    "test_case",
    [
        StandardReuseFromTargetSnapshotErrorTestCase(
            description="raises when reuse_from target resolves no fingerprint schema",
            fingerprint_table_exists=True,
            expected_error_fragment=(
                "model 'orders' reuse origin does not resolve to a fingerprint schema"
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_reuse_from_without_resolved_schema_when_building_snapshot_then_it_raises(
    test_case: StandardReuseFromTargetSnapshotErrorTestCase,
) -> None:
    adapter: StandardReuseFromTargetTestAdapter = StandardReuseFromTargetTestAdapter(
        fingerprint_rows=(),
        existing_relations=frozenset(),
        fingerprint_table_exists=test_case.fingerprint_table_exists,
    )
    unresolved_models: tuple[CompiledModel, ...] = tuple(
        replace(
            model,
            destination=replace(
                model.destination,
                schema=None,
                qualified_name=model.destination.name,
                logical_schema=None,
            ),
        )
        for model in build_standard_reuse_from_target_project().models
    )
    project: CompiledProject = CompiledProject(
        run_id="test_run",
        effective_target_name="dev",
        effective_connection={},
        effective_vars={},
        effective_target_schema=None,
        models=unresolved_models,
    )

    with pytest.raises(PlannerInputError, match=test_case.expected_error_fragment):
        build_standard_reuse_from_target_snapshot(
            project=project,
            adapter=adapter,
            connection=object(),
            scope=build_standard_reuse_from_target_scope(),
            project_config=ProjectConfig(
                name="demo",
                adapter="duckdb",
                targets={
                    "dev": TargetConfig(reuse_from="prod"),
                    "prod": TargetConfig(schema="preserve"),
                },
            ),
            local_config=LocalConfig(),
        )


@pytest.mark.parametrize(
    "test_case",
    [
        StandardReuseFromTargetNoConfigTestCase(
            description="returns none when active target has no reuse_from",
            expected_snapshot=None,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_no_reuse_from_when_building_snapshot_then_it_returns_none(
    test_case: StandardReuseFromTargetNoConfigTestCase,
) -> None:
    adapter: StandardReuseFromTargetTestAdapter = StandardReuseFromTargetTestAdapter(
        fingerprint_rows=(),
        existing_relations=frozenset(),
    )

    snapshot: StandardReuseFromTargetSnapshot | None = build_standard_reuse_from_target_snapshot(
        project=build_standard_reuse_from_target_project(),
        adapter=adapter,
        connection=object(),
        scope=build_standard_reuse_from_target_scope(),
        project_config=ProjectConfig(
            name="demo",
            adapter="duckdb",
            targets={"dev": TargetConfig(schema="dev_schema")},
        ),
        local_config=LocalConfig(),
    )

    assert snapshot is test_case.expected_snapshot
