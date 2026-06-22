from __future__ import annotations

from pathlib import Path

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.selection_staleness._test_types import (
    SelectionStalenessE2ETestCase,
    SelectionStalenessEngineE2ETestCase,
    SelectionStalenessEngineOverride,
)
from tests.e2e.src.sqlbuild.cli.commands.main.selection_staleness.helpers import (
    assert_selection_staleness_case,
)

CORE_SCENARIOS: tuple[SelectionStalenessE2ETestCase, ...] = (
    SelectionStalenessE2ETestCase(
        description="direct changed model parent outside selection leaves child stale and warns",
        project_name="selection_staleness_direct_parent",
        scenario="direct_parent",
        graph="stg_orders -> fact_orders",
        expected_rows_after_baseline=((1, 1.0),),
        expected_rows_after_exact=((1, 1.0),),
        expected_rows_after_repair=((1, 1.25),),
        notes="Exact leaf selection must not silently incorporate an unselected changed parent.",
    ),
    SelectionStalenessE2ETestCase(
        description="multi-hop changed model root outside selection leaves leaf stale and warns",
        project_name="selection_staleness_multi_hop",
        scenario="multi_hop",
        graph="raw_orders_model -> stg_orders -> fact_orders",
        expected_rows_after_baseline=((1, 1.0),),
        expected_rows_after_exact=((1, 1.0),),
        expected_rows_after_repair=((1, 1.25),),
        notes="Warnings should preserve changed root and stale intermediate semantics.",
    ),
    SelectionStalenessE2ETestCase(
        description="selected leaf own-change runs and still warns for unselected changed parent",
        project_name="selection_staleness_leaf_runs_and_warns",
        scenario="leaf_own_change",
        graph="stg_orders -> fact_orders",
        expected_rows_after_baseline=((1, 1.0),),
        expected_rows_after_exact=((1, 2.0),),
        expected_rows_after_repair=((1, 2.25),),
        notes="RUN and STALE are independent: the selected leaf can run and still warn.",
    ),
    SelectionStalenessE2ETestCase(
        description="selected root and leaf warn for unselected stale intermediate",
        project_name="selection_staleness_selected_root_leaf",
        scenario="selected_root_leaf",
        graph="raw_orders_model -> stg_orders -> fact_orders",
        expected_rows_after_baseline=((1, 1.0),),
        expected_rows_after_exact=((1, 1.0),),
        expected_rows_after_repair=((1, 1.25),),
        notes="Selecting a root and leaf does not make the skipped intermediate coherent.",
    ),
    SelectionStalenessE2ETestCase(
        description="mixed selected and unselected changed parents warn only for unselected",
        project_name="selection_staleness_mixed_parents",
        scenario="mixed_parents",
        graph="selected_parent -> fact_orders, unselected_parent -> fact_orders",
        expected_rows_after_baseline=((1, 1.0),),
        expected_rows_after_exact=((1, 1.125),),
        expected_rows_after_repair=((1, 1.25),),
        notes="The selected branch can run while the unselected changed branch still warns.",
    ),
    SelectionStalenessE2ETestCase(
        description="full-refresh selected leaf still warns for unselected changed parent",
        project_name="selection_staleness_full_refresh_leaf",
        scenario="direct_parent",
        graph="stg_orders -> fact_orders",
        expected_rows_after_baseline=((1, 1.0),),
        expected_rows_after_exact=((1, 1.0),),
        expected_rows_after_repair=((1, 1.25),),
        engine_overrides={
            "native": SelectionStalenessEngineOverride(
                exact_command=("--no-color", "build", "--full-refresh", "--select", "fact_orders"),
                expected_exact_stdout_fragments=(
                    "Plan ready (full refresh, 1 selected)",
                    "table     fact_orders",
                    "selected model 'fact_orders' is stale",
                    "stg_orders changed but will not be rebuilt",
                ),
            ),
            "dbt": SelectionStalenessEngineOverride(
                exact_command=(
                    "--no-color",
                    "dbt",
                    "build",
                    "--full-refresh",
                    "--select",
                    "fact_orders",
                ),
                expected_exact_stdout_fragments=(
                    "planned models: 1 run",
                    "fact_orders",
                    "selected dbt model 'fact_orders' is stale",
                    "stg_orders changed but will not be rebuilt or is stale",
                ),
            ),
        },
        notes="Full refresh of a selected leaf does not incorporate an unselected parent.",
    ),
    SelectionStalenessE2ETestCase(
        description="view selected leaf still warns for unselected changed parent",
        project_name="selection_staleness_view_leaf",
        scenario="direct_parent",
        graph="stg_orders -> fact_orders",
        leaf_materialization="view",
        expected_rows_after_baseline=((1, 1.0),),
        expected_rows_after_exact=((1, 1.0),),
        expected_rows_after_repair=((1, 1.25),),
        notes="View materialization must not hide exact-selection stale upstream warnings.",
    ),
    SelectionStalenessE2ETestCase(
        description="changed seed parent outside selection leaves child stale and warns",
        project_name="selection_staleness_seed_parent",
        scenario="seed_parent",
        graph="seed raw_orders -> stg_orders -> fact_orders",
        expected_rows_after_baseline=((1, 1.0),),
        expected_rows_after_exact=((1, 1.0),),
        expected_rows_after_repair=((1, 1.25),),
        notes="Seed changes outside exact selection must warn without silently rebuilding.",
    ),
    SelectionStalenessE2ETestCase(
        description="plan reports staleness without mutating warehouse",
        project_name="selection_staleness_plan_no_mutation",
        scenario="plan_no_mutation",
        graph="stg_orders -> fact_orders",
        engines=("native",),
        engine_overrides={
            "native": SelectionStalenessEngineOverride(
                exact_command=("--no-color", "plan", "--select", "fact_orders"),
                unexpected_exact_stdout_fragments=("Execution  sqb build",),
            )
        },
        expected_rows_after_baseline=((1, 1.0),),
        expected_rows_after_exact=((1, 1.0),),
        expected_rows_after_repair=((1, 1.25),),
        notes="Plan output documents the warning and leaves warehouse data unchanged.",
    ),
    SelectionStalenessE2ETestCase(
        description="later unscoped build repairs stale downstream",
        project_name="selection_staleness_later_unscoped_repair",
        scenario="later_unscoped_repair",
        graph="stg_orders -> fact_orders",
        expected_rows_after_baseline=((1, 1.0),),
        expected_rows_after_exact=((1, 1.0),),
        expected_rows_after_repair=((1, 1.25),),
        notes="A later unscoped build must still know the downstream is stale.",
    ),
    SelectionStalenessE2ETestCase(
        description="repeated exact selection preserves stale warning and warehouse state",
        project_name="selection_staleness_repeated_exact",
        scenario="direct_parent",
        graph="stg_orders -> fact_orders",
        repeat_exact_selection=True,
        expected_rows_after_baseline=((1, 1.0),),
        expected_rows_after_exact=((1, 1.0),),
        expected_rows_after_second_exact=((1, 1.0),),
        expected_rows_after_repair=((1, 1.25),),
        notes="A warning-only exact selection must not mark the stale downstream coherent.",
    ),
    SelectionStalenessE2ETestCase(
        description="diamond graph reports both stale branches",
        project_name="selection_staleness_diamond",
        scenario="diamond",
        graph="raw_orders_model -> stg_orders_a,b -> fact_orders",
        expected_rows_after_baseline=((1, 1.0),),
        expected_rows_after_exact=((1, 1.0),),
        expected_rows_after_repair=((1, 1.25),),
        notes="The branch-complete traversal must not drop either diamond intermediate.",
    ),
)

TEST_CASES: list[SelectionStalenessEngineE2ETestCase] = [
    SelectionStalenessEngineE2ETestCase(
        description=f"{engine}: {scenario.description}",
        engine=engine,
        scenario=scenario,
        expected_rows_after_repair=scenario.expected_rows_after_repair,
    )
    for scenario in CORE_SCENARIOS
    for engine in scenario.engines
]


@pytest.mark.parametrize("test_case", TEST_CASES, ids=[case.description for case in TEST_CASES])
def test_given_exact_selection_when_upstream_changed_then_preserves_staleness_contract(
    test_case: SelectionStalenessEngineE2ETestCase,
    tmp_path: Path,
) -> None:
    assert test_case.expected_rows_after_repair
    assert_selection_staleness_case(tmp_path=tmp_path, test_case=test_case)
