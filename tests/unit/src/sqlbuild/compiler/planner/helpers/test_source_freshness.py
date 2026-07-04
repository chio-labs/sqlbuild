from __future__ import annotations

from typing import Any

import pytest

from sqlbuild.adapters.duckdb.client import DuckDbAdapter
from sqlbuild.compiler.compile.models.core import CompiledProject
from sqlbuild.compiler.planner.helpers.warehouse.source_freshness import (
    build_planner_source_freshness_result,
)
from sqlbuild.compiler.planner.models import PlannerRelationsContext, PlannerScope
from sqlbuild.compiler.source_freshness.models import StandardSourceFreshnessPlanningResult
from sqlbuild.spec.models.source import SourceEntry, SourceFreshnessConfig
from sqlbuild.spec.models.types import SourceFreshnessStrategy, SourceFreshnessValueKind
from tests.unit.src.sqlbuild.compiler.planner.helpers._test_types import (
    PlannerSourceFreshnessReadMapTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    [
        PlannerSourceFreshnessReadMapTestCase(
            description="planner source freshness observes effective source read map",
            expected_observed_data_version="2",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_source_deferral_context_when_building_source_freshness_then_uses_read_map(
    test_case: PlannerSourceFreshnessReadMapTestCase,
) -> None:
    adapter: DuckDbAdapter = DuckDbAdapter()
    connection: Any = adapter.connect({"database": ":memory:"})
    try:
        result: StandardSourceFreshnessPlanningResult = build_planner_source_freshness_result(
            project=CompiledProject(
                run_id="test_run",
                effective_target_name=None,
                effective_connection={},
                effective_vars={},
            ),
            adapter=adapter,
            connection=connection,
            scope=PlannerScope(
                upstream_deps={},
                downstream_deps={},
                all_keys={},
                models_by_name={},
                selected_keys=frozenset(),
                execution_order=(),
            ),
            relations=PlannerRelationsContext(
                model_locations={},
                seed_locations={},
                function_locations={},
                source_map={
                    "raw_orders": SourceEntry(
                        name="raw_orders",
                        freshness=SourceFreshnessConfig(
                            strategy=SourceFreshnessStrategy.SQL,
                            value_kind=SourceFreshnessValueKind.INTEGER,
                            query="SELECT 1 AS data_version",
                        ),
                    )
                },
                source_read_map={
                    "raw_orders": SourceEntry(
                        name="raw_orders",
                        freshness=SourceFreshnessConfig(
                            strategy=SourceFreshnessStrategy.SQL,
                            value_kind=SourceFreshnessValueKind.INTEGER,
                            query="SELECT 2 AS data_version",
                        ),
                    )
                },
                source_warehouse_columns={},
                star_exclude_keyword="EXCLUDE",
            ),
        )
    finally:
        adapter.close(connection)

    assert len(result.observed_records) == 1
    assert result.observed_records[0].data_version == test_case.expected_observed_data_version
