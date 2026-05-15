from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pytest

from sqlbuild.integrations.dagster import SqlBuildDagsterTranslator, sqlbuild_assets
from sqlbuild.integrations.dagster.helpers.assets import build_asset_specs, build_check_specs
from tests.unit.src.sqlbuild.integrations.dagster._test_types import (
    DagsterAssetSpecTestCase,
    DagsterDecoratorTestCase,
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
                ("analytics", "normalize_email"),
                ("analytics", "orders"),
            ),
            expected_model_deps=(("raw", "orders"), ("analytics", "normalize_email")),
            expected_check_names=("audit__not_null__order_id", "audit__freshness__loaded_at"),
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


@pytest.mark.parametrize(
    "test_case",
    [
        DagsterDecoratorTestCase(
            description="decorates user function as dagster assets definition",
            expected_asset_keys=(
                ("raw", "orders"),
                ("analytics", "normalize_email"),
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
