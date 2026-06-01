from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

from sqlbuild.integrations.dagster import (
    SqlBuildDagsterTranslator,
    sqlbuild_assets,
    sqlbuild_scenario_checks,
)
from sqlbuild.integrations.dagster.exceptions import DagsterDagInputError
from sqlbuild.integrations.dagster.helpers.assets import (
    build_asset_specs,
    build_check_specs,
    build_scenario_check_specs,
)
from sqlbuild.integrations.dagster.project import SqlBuildProject
from tests.unit.src.sqlbuild.integrations.dagster._test_types import (
    DagsterAssetCheckFilterTestCase,
    DagsterAssetSpecTestCase,
    DagsterConflictingInputTestCase,
    DagsterDecoratorTestCase,
    DagsterPythonArtifactCompatibilityTestCase,
    DagsterScenarioCheckDecoratorTestCase,
)
from tests.unit.src.sqlbuild.integrations.dagster.helpers import (
    build_dagster_test_dag,
    build_python_augmented_dagster_test_dag,
)

dg: Any = pytest.importorskip("dagster")


@pytest.mark.parametrize(
    "test_case",
    [
        DagsterAssetSpecTestCase(
            description="builds materializable specs and check specs from dag artifact",
            expected_asset_keys=(
                ("raw", "orders"),
                ("shared_order_feed",),
                ("raw_orders_loader",),
                ("analytics", "waffle_types"),
                ("analytics", "normalize_email"),
                ("analytics", "orders"),
                ("analytics", "customers"),
            ),
            expected_model_deps=(("raw", "orders"), ("analytics", "normalize_email")),
            expected_check_names=(
                "audit__not_null__order_id",
                "audit__freshness__loaded_at",
                "scenario__orders_minimal",
                "scenario__customers_minimal",
            ),
            expected_model_selector="orders",
            expected_check_selector="audit:not_null:model:orders:order_id",
            expected_kinds_by_asset_key=(
                (("raw", "orders"), frozenset({"sqlbuild", "source"})),
                (("shared_order_feed",), frozenset({"sqlbuild", "loader"})),
                (("raw_orders_loader",), frozenset({"sqlbuild", "loader"})),
                (("analytics", "waffle_types"), frozenset({"sqlbuild", "seed"})),
                (("analytics", "normalize_email"), frozenset({"sqlbuild", "function"})),
                (("analytics", "customers"), frozenset({"sqlbuild", "view"})),
                (("analytics", "orders"), frozenset({"sqlbuild", "table"})),
            ),
            expected_group_names=("dagster_project",),
        )
    ],
    ids=["builds materializable specs and check specs from dag artifact"],
)
def test_given_sqlbuild_dag_when_building_specs_then_maps_assets_deps_and_checks(
    test_case: DagsterAssetSpecTestCase,
) -> None:
    dag: Mapping[str, Any] = build_dagster_test_dag()
    translator: SqlBuildDagsterTranslator = SqlBuildDagsterTranslator()
    asset_specs: tuple[Any, ...] = build_asset_specs(dag=dag, translator=translator)
    check_specs: tuple[Any, ...] = build_check_specs(dag=dag, translator=translator)
    asset_keys: tuple[tuple[str, ...], ...] = tuple(tuple(spec.key.path) for spec in asset_specs)
    model_spec: Any = next(
        spec for spec in asset_specs if tuple(spec.key.path) == ("analytics", "orders")
    )

    assert asset_keys == test_case.expected_asset_keys
    assert tuple(tuple(dep.asset_key.path) for dep in model_spec.deps) == (
        test_case.expected_model_deps
    )
    assert tuple(spec.name for spec in check_specs) == test_case.expected_check_names
    assert model_spec.metadata["sqlbuild_selector"] == test_case.expected_model_selector
    assert check_specs[0].metadata["sqlbuild_check_selector"] == test_case.expected_check_selector
    assert {tuple(spec.key.path): frozenset(spec.kinds) for spec in asset_specs} == dict(
        test_case.expected_kinds_by_asset_key
    )
    assert (
        tuple(sorted({spec.group_name for spec in asset_specs})) == test_case.expected_group_names
    )


@pytest.mark.parametrize(
    "test_case",
    [
        DagsterPythonArtifactCompatibilityTestCase(
            description="maps Python DAG artifact additions into asset and check specs",
            expected_asset_keys=(
                ("raw", "orders"),
                ("shared_order_feed",),
                ("raw_orders_loader",),
                ("analytics", "waffle_types"),
                ("analytics", "normalize_email"),
                ("analytics", "orders"),
                ("analytics", "customers"),
                ("task", "prepare_orders"),
                ("asset", "orders_export"),
            ),
            expected_check_names=(
                "audit__not_null__order_id",
                "audit__freshness__loaded_at",
                "scenario__orders_minimal",
                "scenario__customers_minimal",
                "python_check__check_orders_export",
            ),
            expected_task_deps=(("analytics", "orders"),),
            expected_asset_deps=(("task", "prepare_orders"),),
            expected_python_kinds_by_asset_key=(
                (("task", "prepare_orders"), frozenset({"sqlbuild", "task"})),
                (("asset", "orders_export"), frozenset({"sqlbuild", "asset"})),
            ),
            expected_task_group="python",
            expected_asset_group="exports",
            expected_asset_metadata_keys=(
                "columns",
                "column_lineage",
                "materialization_type",
            ),
        )
    ],
    ids=["maps Python DAG artifact additions into asset and check specs"],
)
def test_given_python_augmented_dag_when_building_specs_then_maps_python_nodes(
    test_case: DagsterPythonArtifactCompatibilityTestCase,
) -> None:
    dag: Mapping[str, Any] = build_python_augmented_dagster_test_dag()
    translator: SqlBuildDagsterTranslator = SqlBuildDagsterTranslator()

    asset_specs: tuple[Any, ...] = build_asset_specs(dag=dag, translator=translator)
    check_specs: tuple[Any, ...] = build_check_specs(dag=dag, translator=translator)
    task_spec: Any = next(
        spec for spec in asset_specs if tuple(spec.key.path) == ("task", "prepare_orders")
    )
    python_asset_spec: Any = next(
        spec for spec in asset_specs if tuple(spec.key.path) == ("asset", "orders_export")
    )

    assert tuple(tuple(spec.key.path) for spec in asset_specs) == test_case.expected_asset_keys
    assert tuple(spec.name for spec in check_specs) == test_case.expected_check_names
    assert (
        tuple(tuple(dep.asset_key.path) for dep in task_spec.deps) == test_case.expected_task_deps
    )
    assert tuple(tuple(dep.asset_key.path) for dep in python_asset_spec.deps) == (
        test_case.expected_asset_deps
    )
    assert {
        tuple(spec.key.path): frozenset(spec.kinds) for spec in (task_spec, python_asset_spec)
    } == dict(test_case.expected_python_kinds_by_asset_key)
    assert task_spec.group_name == test_case.expected_task_group
    assert python_asset_spec.group_name == test_case.expected_asset_group
    assert all(key in python_asset_spec.metadata for key in test_case.expected_asset_metadata_keys)


@pytest.mark.parametrize(
    "test_case",
    [
        DagsterDecoratorTestCase(
            description="decorates user function as dagster assets definition",
            expected_asset_keys=(
                ("raw", "orders"),
                ("shared_order_feed",),
                ("raw_orders_loader",),
                ("analytics", "waffle_types"),
                ("analytics", "normalize_email"),
                ("analytics", "customers"),
                ("analytics", "orders"),
            ),
        )
    ],
    ids=["decorates user function as dagster assets definition"],
)
def test_given_sqlbuild_assets_decorator_when_applied_then_returns_assets_definition(
    test_case: DagsterDecoratorTestCase,
) -> None:
    @sqlbuild_assets(dag=build_dagster_test_dag())
    def assets_def() -> dg.MaterializeResult:
        return dg.MaterializeResult()

    assert tuple(sorted(tuple(key.path) for key in assets_def.keys)) == tuple(
        sorted(test_case.expected_asset_keys)
    )


@pytest.mark.parametrize(
    "test_case",
    [
        DagsterScenarioCheckDecoratorTestCase(
            description="decorates user function as scenario-only asset checks definition",
            expected_check_names=("scenario__orders_minimal", "scenario__customers_minimal"),
            unexpected_check_names=("audit__not_null__order_id", "audit__freshness__loaded_at"),
        )
    ],
    ids=["decorates user function as scenario-only asset checks definition"],
)
def test_given_sqlbuild_scenario_checks_decorator_when_applied_then_returns_check_definition(
    test_case: DagsterScenarioCheckDecoratorTestCase,
) -> None:
    @sqlbuild_scenario_checks(dag=build_dagster_test_dag())
    def checks_def() -> dg.AssetCheckResult:
        return dg.AssetCheckResult(
            passed=True,
            asset_key=dg.AssetKey(["analytics", "orders"]),
            check_name="scenario__orders_minimal",
        )

    check_names: tuple[str, ...] = tuple(spec.name for spec in checks_def.check_specs)

    assert check_names == test_case.expected_check_names
    assert not set(test_case.unexpected_check_names).intersection(check_names)


@pytest.mark.parametrize(
    "test_case",
    [
        DagsterScenarioCheckDecoratorTestCase(
            description="builds scenario-only check specs",
            expected_check_names=("scenario__orders_minimal", "scenario__customers_minimal"),
            unexpected_check_names=("audit__not_null__order_id", "audit__freshness__loaded_at"),
        )
    ],
    ids=["builds scenario-only check specs"],
)
def test_given_sqlbuild_dag_when_building_scenario_check_specs_then_filters_non_scenarios(
    test_case: DagsterScenarioCheckDecoratorTestCase,
) -> None:
    check_specs: tuple[Any, ...] = build_scenario_check_specs(
        dag=build_dagster_test_dag(),
        translator=SqlBuildDagsterTranslator(),
    )
    check_names: tuple[str, ...] = tuple(spec.name for spec in check_specs)

    assert check_names == test_case.expected_check_names
    assert not set(test_case.unexpected_check_names).intersection(check_names)


@pytest.mark.parametrize(
    "test_case",
    [
        DagsterConflictingInputTestCase(
            description="assets decorator rejects dag and project together",
            expected_error_fragment="sqlbuild_assets received both 'dag' and 'project'",
            expected_error_code="I002",
        )
    ],
    ids=["assets decorator rejects dag and project together"],
)
def test_given_dag_and_project_when_building_assets_decorator_then_raises_coded_input_error(
    test_case: DagsterConflictingInputTestCase,
) -> None:
    project: SqlBuildProject = SqlBuildProject(project_dir=Path("."))

    with pytest.raises(DagsterDagInputError, match=test_case.expected_error_fragment) as error:
        sqlbuild_assets(dag=build_dagster_test_dag(), project=project)

    assert error.value.code == test_case.expected_error_code


@pytest.mark.parametrize(
    "test_case",
    [
        DagsterConflictingInputTestCase(
            description="scenario checks decorator rejects dag and project together",
            expected_error_fragment="sqlbuild_scenario_checks received both 'dag' and 'project'",
            expected_error_code="I002",
        )
    ],
    ids=["scenario checks decorator rejects dag and project together"],
)
def test_given_dag_and_project_when_building_scenario_checks_then_raises_coded_input_error(
    test_case: DagsterConflictingInputTestCase,
) -> None:
    project: SqlBuildProject = SqlBuildProject(project_dir=Path("."))

    with pytest.raises(DagsterDagInputError, match=test_case.expected_error_fragment) as error:
        sqlbuild_scenario_checks(dag=build_dagster_test_dag(), project=project)

    assert error.value.code == test_case.expected_error_code


@pytest.mark.parametrize(
    "test_case",
    [
        DagsterAssetCheckFilterTestCase(
            description="excludes scenario checks when requested",
            expected_check_names=("audit__not_null__order_id", "audit__freshness__loaded_at"),
            unexpected_check_names=("scenario__orders_minimal", "scenario__customers_minimal"),
        )
    ],
    ids=["excludes scenario checks when requested"],
)
def test_given_sqlbuild_dag_when_building_check_specs_then_can_exclude_scenarios(
    test_case: DagsterAssetCheckFilterTestCase,
) -> None:
    check_specs: tuple[Any, ...] = build_check_specs(
        dag=build_dagster_test_dag(),
        translator=SqlBuildDagsterTranslator(),
        include_scenarios=False,
    )
    check_names: tuple[str, ...] = tuple(spec.name for spec in check_specs)

    assert check_names == test_case.expected_check_names
    assert not set(test_case.unexpected_check_names).intersection(check_names)
