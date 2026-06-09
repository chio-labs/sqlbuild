from __future__ import annotations

import pytest

from sqlbuild.compiler.compile.models.core import CompiledProject
from sqlbuild.compiler.planner.exceptions import PlannerInputError
from sqlbuild.compiler.planner.helpers.standard_reuse_from_target import (
    build_standard_reuse_from_target_snapshot,
)
from sqlbuild.compiler.planner.models import PlannerScope, StandardReuseFromTargetSnapshot
from sqlbuild.spec.models.project import LocalConfig, ProjectConfig, TargetConfig
from tests.unit.src.sqlbuild.compiler.planner.helpers._test_types import (
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

STANDARD_REUSE_FROM_TARGET_SNAPSHOT_ERROR_TEST_CASES: list[
    StandardReuseFromTargetSnapshotErrorTestCase
] = [
    StandardReuseFromTargetSnapshotErrorTestCase(
        description="raises when reuse_from fingerprint table is missing",
        fingerprint_table_exists=False,
        expected_error_fragment="cannot read fingerprint state for reuse_from target 'prod'",
    ),
    StandardReuseFromTargetSnapshotErrorTestCase(
        description="raises when reuse_from fingerprint rows cannot be read",
        fingerprint_table_exists=True,
        fingerprint_read_fails=True,
        expected_error_fragment="cannot read fingerprint state for reuse_from target 'prod'",
    ),
]


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
            expected_fingerprint_schema="prod_schema",
            expected_model_relation_exists={"orders": True, "customers": False},
            expected_model_built_version_hashes={
                "orders": "orders_version_hash",
                "customers": None,
            },
        )
    ],
    ids=["reads reuse_from fingerprints and relation existence"],
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
    assert snapshot.fingerprint_database == test_case.expected_fingerprint_database
    assert snapshot.fingerprint_schema == test_case.expected_fingerprint_schema
    assert {
        model_name: model_snapshot.relation_exists
        for model_name, model_snapshot in snapshot.model_snapshots.items()
    } == test_case.expected_model_relation_exists
    assert {
        model_name: model_snapshot.built_version_hash
        for model_name, model_snapshot in snapshot.model_snapshots.items()
    } == test_case.expected_model_built_version_hashes


@pytest.mark.parametrize(
    "test_case",
    STANDARD_REUSE_FROM_TARGET_SNAPSHOT_ERROR_TEST_CASES,
    ids=[case.description for case in STANDARD_REUSE_FROM_TARGET_SNAPSHOT_ERROR_TEST_CASES],
)
def test_given_missing_reuse_from_fingerprint_state_when_building_snapshot_then_it_raises(
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
            expected_fingerprint_schema="prod_dev_schema",
            expected_fingerprint_database="warehouse",
            expected_model_relation_exists={"orders": True, "customers": False},
            expected_model_built_version_hashes={
                "orders": "orders_version_hash",
                "customers": None,
            },
        )
    ],
    ids=["resolves templated reuse_from target namespace"],
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
                    schema="${schema_prefix}_${CTX:schema}",
                    vars={"db": "warehouse", "schema_prefix": "prod"},
                ),
            },
        ),
        local_config=LocalConfig(),
    )

    assert snapshot is not None
    assert snapshot.fingerprint_database == test_case.expected_fingerprint_database
    assert snapshot.fingerprint_schema == test_case.expected_fingerprint_schema
    assert {
        model_name: model_snapshot.relation_exists
        for model_name, model_snapshot in snapshot.model_snapshots.items()
    } == test_case.expected_model_relation_exists


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
            expected_fingerprint_schema="prod_schema",
            expected_model_relation_exists={"orders": True},
            expected_model_built_version_hashes={"orders": "orders_version_hash"},
            expected_model_names=("orders",),
            selected_model_names=frozenset({"orders"}),
        )
    ],
    ids=["includes only selected models"],
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
                "reuse_from target 'prod' does not resolve to a fingerprint schema"
            ),
        )
    ],
    ids=["raises when reuse_from target resolves no fingerprint schema"],
)
def test_given_reuse_from_without_resolved_schema_when_building_snapshot_then_it_raises(
    test_case: StandardReuseFromTargetSnapshotErrorTestCase,
) -> None:
    adapter: StandardReuseFromTargetTestAdapter = StandardReuseFromTargetTestAdapter(
        fingerprint_rows=(),
        existing_relations=frozenset(),
        fingerprint_table_exists=test_case.fingerprint_table_exists,
    )
    project: CompiledProject = CompiledProject(
        run_id="test_run",
        effective_target_name="dev",
        effective_connection={},
        effective_vars={},
        effective_target_schema=None,
        models=build_standard_reuse_from_target_project().models,
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
    ids=["returns none when active target has no reuse_from"],
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
