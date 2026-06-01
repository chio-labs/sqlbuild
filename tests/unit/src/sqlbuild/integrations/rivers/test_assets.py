from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pytest

from sqlbuild.integrations.rivers.helpers import assets as rivers_assets
from sqlbuild.integrations.rivers.helpers.assets import build_asset_defs
from sqlbuild.integrations.rivers.translator import SqlBuildRiversTranslator
from tests.unit.src.sqlbuild.integrations.dagster.helpers import (
    build_python_augmented_dagster_test_dag,
)
from tests.unit.src.sqlbuild.integrations.rivers._test_types import (
    RiversPythonArtifactCompatibilityTestCase,
)
from tests.unit.src.sqlbuild.integrations.rivers.helpers import FakeRiversModule


@pytest.mark.parametrize(
    "test_case",
    [
        RiversPythonArtifactCompatibilityTestCase(
            description="consumes Python DAG artifact additions without changing SQL assets",
            expected_asset_names=(
                "raw__orders",
                "shared_order_feed",
                "raw_orders_loader",
                "analytics__waffle_types",
                "analytics__normalize_email",
                "analytics__orders",
                "analytics__customers",
            ),
            expected_order_deps=("raw__orders", "analytics__normalize_email"),
        )
    ],
    ids=["consumes Python DAG artifact additions without changing SQL assets"],
)
def test_given_python_augmented_dag_when_building_asset_defs_then_remains_compatible(
    test_case: RiversPythonArtifactCompatibilityTestCase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dag: Mapping[str, Any] = build_python_augmented_dagster_test_dag()
    monkeypatch.setattr(rivers_assets, "load_rivers", lambda: FakeRiversModule())

    asset_defs: tuple[Any, ...] = build_asset_defs(
        dag=dag,
        translator=SqlBuildRiversTranslator(),
    )
    order_def: Any = next(asset for asset in asset_defs if asset.name == "analytics__orders")

    assert tuple(asset.name for asset in asset_defs) == test_case.expected_asset_names
    assert tuple(dep.name for dep in order_def.deps) == test_case.expected_order_deps
