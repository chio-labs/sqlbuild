from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pytest

from sqlbuild.integrations.dagster import (
    SqlBuildDagsterTranslator,
    sqlbuild_assets,
    sqlbuild_scenario_checks,
)
from sqlbuild.integrations.dagster.helpers.assets import (
    build_asset_specs,
    build_check_specs,
    build_scenario_check_specs,
)
from tests.unit.src.sqlbuild.integrations.dagster._test_types import (
    DagsterAssetCheckFilterTestCase,
    DagsterAssetSpecTestCase,
    DagsterDecoratorTestCase,
    DagsterScenarioCheckDecoratorTestCase,
)
from tests.unit.src.sqlbuild.integrations.dagster.helpers import build_dagster_test_dag

dg: Any = pytest.importorskip("dagster")


@pytest.mark.parametrize(
    "test_case",
    [
        DagsterAssetSpecTestCase(
            description="builds materializable specs and check specs from dag artifact",
            expected_asset_keys=(
                ("raw", "orders"),
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
    assert tuple(sorted({spec.group_name for spec in asset_specs})) == test_case.expected_group_names


@pytest.mark.parametrize(
    "test_case",
    [
        DagsterDecoratorTestCase(
            description="decorates user function as dagster assets definition",
            expected_asset_keys=(
                ("raw", "orders"),
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
