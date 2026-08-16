from __future__ import annotations

from pathlib import Path

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.selection_staleness._test_types import (
    SelectionStalenessEngineE2ETestCase,
)
from tests.e2e.src.sqlbuild.cli.commands.main.selection_staleness.helpers import (
    assert_native_selection_staleness_case,
    assert_selection_staleness_case,
    native_diamond_files,
    native_direct_files,
    native_mixed_parent_files,
    native_multi_hop_files,
    native_seed_parent_files,
)

_NATIVE_BASELINE_COMMAND: tuple[str, ...] = (
    "--no-color",
    "build",
    "--select",
    "+fact_orders",
)
_NATIVE_EXACT_COMMAND: tuple[str, ...] = (
    "--no-color",
    "build",
    "--changes-only",
    "--select",
    "fact_orders",
)
_NATIVE_REPAIR_COMMAND: tuple[str, ...] = (
    "--no-color",
    "build",
    "--changes-only",
    "--select",
    "+fact_orders",
)
_NATIVE_DATABASE_PATH: Path = Path("warehouse.duckdb")
_NATIVE_FACT_ROWS_QUERY: str = "SELECT order_id, amount_dollars FROM fact_orders ORDER BY order_id"
_NATIVE_STALENESS_LABEL: str = "selected model 'fact_orders' will build on"


@pytest.mark.parametrize(
    "test_case",
    [
        SelectionStalenessEngineE2ETestCase(
            description="native: direct changed model parent outside selection leaves child stale and warns",
            project_name="native_selection_staleness_direct_parent",
            graph="stg_orders -> fact_orders",
            runner=assert_native_selection_staleness_case,
            baseline_files=native_direct_files(
                amount_cents=100, fact_adjustment=0, leaf_materialization="table"
            ),
            mutated_files=native_direct_files(
                amount_cents=125, fact_adjustment=0, leaf_materialization="table"
            ),
            baseline_command=_NATIVE_BASELINE_COMMAND,
            exact_commands=(_NATIVE_EXACT_COMMAND,),
            repair_command=_NATIVE_REPAIR_COMMAND,
            expected_exact_stdout_fragments=(_NATIVE_STALENESS_LABEL, "- stg_orders"),
            unexpected_exact_stdout_fragments=("table    stg_orders",),
            expected_repair_stdout_fragments=(
                "Plan ready (2 selected)",
                "table     stg_orders",
            ),
            unexpected_repair_stdout_fragments=(_NATIVE_STALENESS_LABEL,),
            expected_rows_after_baseline=((1, 1.0),),
            expected_rows_after_exact_commands=(((1, 1.0),),),
            expected_rows_after_repair=((1, 1.25),),
            database_relative_path=_NATIVE_DATABASE_PATH,
            fact_rows_query=_NATIVE_FACT_ROWS_QUERY,
            notes="Exact leaf selection must not silently incorporate an unselected changed parent.",
        ),
        SelectionStalenessEngineE2ETestCase(
            description="native: multi-hop changed model root outside selection leaves leaf stale and warns",
            project_name="native_selection_staleness_multi_hop",
            graph="raw_orders_model -> stg_orders -> fact_orders",
            runner=assert_native_selection_staleness_case,
            baseline_files=native_multi_hop_files(
                amount_cents=100, fact_adjustment=0, leaf_materialization="table"
            ),
            mutated_files=native_multi_hop_files(
                amount_cents=125, fact_adjustment=0, leaf_materialization="table"
            ),
            baseline_command=_NATIVE_BASELINE_COMMAND,
            exact_commands=(_NATIVE_EXACT_COMMAND,),
            repair_command=_NATIVE_REPAIR_COMMAND,
            expected_exact_stdout_fragments=(
                _NATIVE_STALENESS_LABEL,
                "- raw_orders_model",
                "- stg_orders",
            ),
            unexpected_exact_stdout_fragments=(
                "table    raw_orders_model",
                "table    stg_orders",
            ),
            expected_repair_stdout_fragments=(
                "Plan ready (3 selected)",
                "table     raw_orders_model",
                "table     stg_orders",
            ),
            unexpected_repair_stdout_fragments=(_NATIVE_STALENESS_LABEL,),
            expected_rows_after_baseline=((1, 1.0),),
            expected_rows_after_exact_commands=(((1, 1.0),),),
            expected_rows_after_repair=((1, 1.25),),
            database_relative_path=_NATIVE_DATABASE_PATH,
            fact_rows_query=_NATIVE_FACT_ROWS_QUERY,
            notes="Warnings should preserve changed root and stale intermediate semantics.",
        ),
        SelectionStalenessEngineE2ETestCase(
            description="native: selected leaf own-change runs and still warns for unselected changed parent",
            project_name="native_selection_staleness_leaf_runs_and_warns",
            graph="stg_orders -> fact_orders",
            runner=assert_native_selection_staleness_case,
            baseline_files=native_direct_files(
                amount_cents=100, fact_adjustment=0, leaf_materialization="table"
            ),
            mutated_files=native_direct_files(
                amount_cents=125, fact_adjustment=1, leaf_materialization="table"
            ),
            baseline_command=_NATIVE_BASELINE_COMMAND,
            exact_commands=(_NATIVE_EXACT_COMMAND,),
            repair_command=_NATIVE_REPAIR_COMMAND,
            expected_exact_stdout_fragments=(
                "fact_orders",
                _NATIVE_STALENESS_LABEL,
                "- stg_orders",
            ),
            unexpected_exact_stdout_fragments=("table    stg_orders",),
            expected_repair_stdout_fragments=(
                "Plan ready (2 selected)",
                "table     stg_orders",
            ),
            unexpected_repair_stdout_fragments=(_NATIVE_STALENESS_LABEL,),
            expected_rows_after_baseline=((1, 1.0),),
            expected_rows_after_exact_commands=(((1, 2.0),),),
            expected_rows_after_repair=((1, 2.25),),
            database_relative_path=_NATIVE_DATABASE_PATH,
            fact_rows_query=_NATIVE_FACT_ROWS_QUERY,
            notes="RUN and STALE are independent: the selected leaf can run and still warn.",
        ),
        SelectionStalenessEngineE2ETestCase(
            description="native: selected root and leaf warn for unselected stale intermediate",
            project_name="native_selection_staleness_selected_root_leaf",
            graph="raw_orders_model -> stg_orders -> fact_orders",
            runner=assert_native_selection_staleness_case,
            baseline_files=native_multi_hop_files(
                amount_cents=100, fact_adjustment=0, leaf_materialization="table"
            ),
            mutated_files=native_multi_hop_files(
                amount_cents=125, fact_adjustment=0, leaf_materialization="table"
            ),
            baseline_command=_NATIVE_BASELINE_COMMAND,
            exact_commands=(
                (
                    "--no-color",
                    "build",
                    "--changes-only",
                    "--select",
                    "raw_orders_model",
                    "fact_orders",
                ),
            ),
            repair_command=_NATIVE_REPAIR_COMMAND,
            expected_exact_stdout_fragments=(
                "raw_orders_model",
                _NATIVE_STALENESS_LABEL,
                "- stg_orders",
            ),
            unexpected_exact_stdout_fragments=("table    stg_orders",),
            expected_repair_stdout_fragments=("Plan ready (2 selected)",),
            unexpected_repair_stdout_fragments=(_NATIVE_STALENESS_LABEL,),
            expected_rows_after_baseline=((1, 1.0),),
            expected_rows_after_exact_commands=(((1, 1.0),),),
            expected_rows_after_repair=((1, 1.25),),
            database_relative_path=_NATIVE_DATABASE_PATH,
            fact_rows_query=_NATIVE_FACT_ROWS_QUERY,
            notes="Selecting a root and leaf does not make the skipped intermediate coherent.",
        ),
        SelectionStalenessEngineE2ETestCase(
            description="native: mixed selected and unselected changed parents warn only for unselected",
            project_name="native_selection_staleness_mixed_parents",
            graph="selected_parent -> fact_orders, unselected_parent -> fact_orders",
            runner=assert_native_selection_staleness_case,
            baseline_files=native_mixed_parent_files(
                amount_cents=100, leaf_materialization="table"
            ),
            mutated_files=native_mixed_parent_files(amount_cents=125, leaf_materialization="table"),
            baseline_command=_NATIVE_BASELINE_COMMAND,
            exact_commands=(
                (
                    "--no-color",
                    "build",
                    "--changes-only",
                    "--select",
                    "selected_parent",
                    "fact_orders",
                ),
            ),
            repair_command=_NATIVE_REPAIR_COMMAND,
            expected_exact_stdout_fragments=(
                "selected_parent",
                "fact_orders",
                _NATIVE_STALENESS_LABEL,
                "- unselected_parent",
            ),
            unexpected_exact_stdout_fragments=("- selected_parent",),
            expected_repair_stdout_fragments=("Plan ready (2 selected)",),
            unexpected_repair_stdout_fragments=(_NATIVE_STALENESS_LABEL,),
            expected_rows_after_baseline=((1, 1.0),),
            expected_rows_after_exact_commands=(((1, 1.125),),),
            expected_rows_after_repair=((1, 1.25),),
            database_relative_path=_NATIVE_DATABASE_PATH,
            fact_rows_query=_NATIVE_FACT_ROWS_QUERY,
            notes="The selected branch can run while the unselected changed branch still warns.",
        ),
        SelectionStalenessEngineE2ETestCase(
            description="native: full-refresh selected leaf still warns for unselected changed parent",
            project_name="native_selection_staleness_full_refresh_leaf",
            graph="stg_orders -> fact_orders",
            runner=assert_native_selection_staleness_case,
            baseline_files=native_direct_files(
                amount_cents=100, fact_adjustment=0, leaf_materialization="table"
            ),
            mutated_files=native_direct_files(
                amount_cents=125, fact_adjustment=0, leaf_materialization="table"
            ),
            baseline_command=_NATIVE_BASELINE_COMMAND,
            exact_commands=(
                (
                    "--no-color",
                    "build",
                    "--full-refresh",
                    "--select",
                    "fact_orders",
                ),
            ),
            repair_command=_NATIVE_REPAIR_COMMAND,
            expected_exact_stdout_fragments=(
                "Plan ready (full refresh, 1 selected)",
                "table     fact_orders",
                _NATIVE_STALENESS_LABEL,
                "- stg_orders",
            ),
            unexpected_exact_stdout_fragments=("table    stg_orders",),
            expected_repair_stdout_fragments=(
                "Plan ready (2 selected)",
                "table     stg_orders",
            ),
            unexpected_repair_stdout_fragments=(_NATIVE_STALENESS_LABEL,),
            expected_rows_after_baseline=((1, 1.0),),
            expected_rows_after_exact_commands=(((1, 1.0),),),
            expected_rows_after_repair=((1, 1.25),),
            database_relative_path=_NATIVE_DATABASE_PATH,
            fact_rows_query=_NATIVE_FACT_ROWS_QUERY,
            notes="Full refresh of a selected leaf does not incorporate an unselected parent.",
        ),
        SelectionStalenessEngineE2ETestCase(
            description="native: view selected leaf still warns for unselected changed parent",
            project_name="native_selection_staleness_view_leaf",
            graph="stg_orders -> fact_orders",
            runner=assert_native_selection_staleness_case,
            baseline_files=native_direct_files(
                amount_cents=100, fact_adjustment=0, leaf_materialization="view"
            ),
            mutated_files=native_direct_files(
                amount_cents=125, fact_adjustment=0, leaf_materialization="view"
            ),
            baseline_command=_NATIVE_BASELINE_COMMAND,
            exact_commands=(_NATIVE_EXACT_COMMAND,),
            repair_command=_NATIVE_REPAIR_COMMAND,
            expected_exact_stdout_fragments=(_NATIVE_STALENESS_LABEL, "- stg_orders"),
            unexpected_exact_stdout_fragments=("table    stg_orders",),
            expected_repair_stdout_fragments=(
                "Plan ready (2 selected)",
                "table     stg_orders",
            ),
            unexpected_repair_stdout_fragments=(_NATIVE_STALENESS_LABEL,),
            expected_rows_after_baseline=((1, 1.0),),
            expected_rows_after_exact_commands=(((1, 1.0),),),
            expected_rows_after_repair=((1, 1.25),),
            database_relative_path=_NATIVE_DATABASE_PATH,
            fact_rows_query=_NATIVE_FACT_ROWS_QUERY,
            notes="View materialization must not hide exact-selection stale upstream warnings.",
        ),
        SelectionStalenessEngineE2ETestCase(
            description="native: changed seed parent outside selection leaves child stale and warns",
            project_name="native_selection_staleness_seed_parent",
            graph="seed order_amounts -> stg_orders -> fact_orders",
            runner=assert_native_selection_staleness_case,
            baseline_files=native_seed_parent_files(
                amount_cents=100, fact_adjustment=0, leaf_materialization="table"
            ),
            mutated_files=native_seed_parent_files(
                amount_cents=125, fact_adjustment=0, leaf_materialization="table"
            ),
            baseline_command=_NATIVE_BASELINE_COMMAND,
            exact_commands=(_NATIVE_EXACT_COMMAND,),
            repair_command=_NATIVE_REPAIR_COMMAND,
            expected_exact_stdout_fragments=(
                _NATIVE_STALENESS_LABEL,
                "- order_amounts",
            ),
            unexpected_exact_stdout_fragments=("table    stg_orders",),
            expected_repair_stdout_fragments=(
                "Plan ready (3 selected)",
                "seed      order_amounts",
                "table     stg_orders",
            ),
            unexpected_repair_stdout_fragments=(_NATIVE_STALENESS_LABEL,),
            expected_rows_after_baseline=((1, 1.0),),
            expected_rows_after_exact_commands=(((1, 1.0),),),
            expected_rows_after_repair=((1, 1.25),),
            database_relative_path=_NATIVE_DATABASE_PATH,
            fact_rows_query=_NATIVE_FACT_ROWS_QUERY,
            notes="Seed changes outside exact selection must warn without silently rebuilding.",
        ),
        SelectionStalenessEngineE2ETestCase(
            description="native: plan reports staleness without mutating warehouse",
            project_name="native_selection_staleness_plan_no_mutation",
            graph="stg_orders -> fact_orders",
            runner=assert_native_selection_staleness_case,
            baseline_files=native_direct_files(
                amount_cents=100, fact_adjustment=0, leaf_materialization="table"
            ),
            mutated_files=native_direct_files(
                amount_cents=125, fact_adjustment=0, leaf_materialization="table"
            ),
            baseline_command=_NATIVE_BASELINE_COMMAND,
            exact_commands=(("--no-color", "plan", "--changes-only", "--select", "fact_orders"),),
            repair_command=_NATIVE_REPAIR_COMMAND,
            expected_exact_stdout_fragments=(
                "Plan ready (0 selected)",
                _NATIVE_STALENESS_LABEL,
                "- stg_orders",
            ),
            unexpected_exact_stdout_fragments=(
                "table    stg_orders",
                "Execution  sqb build",
            ),
            expected_repair_stdout_fragments=(
                "Plan ready (2 selected)",
                "table     stg_orders",
            ),
            unexpected_repair_stdout_fragments=(_NATIVE_STALENESS_LABEL,),
            expected_rows_after_baseline=((1, 1.0),),
            expected_rows_after_exact_commands=(((1, 1.0),),),
            expected_rows_after_repair=((1, 1.25),),
            database_relative_path=_NATIVE_DATABASE_PATH,
            fact_rows_query=_NATIVE_FACT_ROWS_QUERY,
            notes="Plan output documents the warning and leaves warehouse data unchanged.",
        ),
        SelectionStalenessEngineE2ETestCase(
            description="native: later unscoped build repairs stale downstream",
            project_name="native_selection_staleness_later_unscoped_repair",
            graph="stg_orders -> fact_orders",
            runner=assert_native_selection_staleness_case,
            baseline_files=native_direct_files(
                amount_cents=100, fact_adjustment=0, leaf_materialization="table"
            ),
            mutated_files=native_direct_files(
                amount_cents=125, fact_adjustment=0, leaf_materialization="table"
            ),
            baseline_command=_NATIVE_BASELINE_COMMAND,
            exact_commands=(_NATIVE_EXACT_COMMAND,),
            repair_command=("--no-color", "build"),
            expected_exact_stdout_fragments=(_NATIVE_STALENESS_LABEL,),
            unexpected_exact_stdout_fragments=(),
            expected_repair_stdout_fragments=("Plan ready (2 selected)",),
            unexpected_repair_stdout_fragments=(_NATIVE_STALENESS_LABEL,),
            expected_rows_after_baseline=((1, 1.0),),
            expected_rows_after_exact_commands=(((1, 1.0),),),
            expected_rows_after_repair=((1, 1.25),),
            database_relative_path=_NATIVE_DATABASE_PATH,
            fact_rows_query=_NATIVE_FACT_ROWS_QUERY,
            notes="A later unscoped build must still know the downstream is stale.",
        ),
        SelectionStalenessEngineE2ETestCase(
            description="native: repeated exact selection preserves stale warning and warehouse state",
            project_name="native_selection_staleness_repeated_exact",
            graph="stg_orders -> fact_orders",
            runner=assert_native_selection_staleness_case,
            baseline_files=native_direct_files(
                amount_cents=100, fact_adjustment=0, leaf_materialization="table"
            ),
            mutated_files=native_direct_files(
                amount_cents=125, fact_adjustment=0, leaf_materialization="table"
            ),
            baseline_command=_NATIVE_BASELINE_COMMAND,
            exact_commands=(_NATIVE_EXACT_COMMAND, _NATIVE_EXACT_COMMAND),
            repair_command=_NATIVE_REPAIR_COMMAND,
            expected_exact_stdout_fragments=(_NATIVE_STALENESS_LABEL, "- stg_orders"),
            unexpected_exact_stdout_fragments=("table    stg_orders",),
            expected_repair_stdout_fragments=(
                "Plan ready (2 selected)",
                "table     stg_orders",
            ),
            unexpected_repair_stdout_fragments=(_NATIVE_STALENESS_LABEL,),
            expected_rows_after_baseline=((1, 1.0),),
            expected_rows_after_exact_commands=(((1, 1.0),), ((1, 1.0),)),
            expected_rows_after_repair=((1, 1.25),),
            database_relative_path=_NATIVE_DATABASE_PATH,
            fact_rows_query=_NATIVE_FACT_ROWS_QUERY,
            notes="A warning-only exact selection must not mark the stale downstream coherent.",
        ),
        SelectionStalenessEngineE2ETestCase(
            description="native: diamond graph reports both stale branches",
            project_name="native_selection_staleness_diamond",
            graph="raw_orders_model -> stg_orders_a,b -> fact_orders",
            runner=assert_native_selection_staleness_case,
            baseline_files=native_diamond_files(amount_cents=100, leaf_materialization="table"),
            mutated_files=native_diamond_files(amount_cents=125, leaf_materialization="table"),
            baseline_command=_NATIVE_BASELINE_COMMAND,
            exact_commands=(_NATIVE_EXACT_COMMAND,),
            repair_command=_NATIVE_REPAIR_COMMAND,
            expected_exact_stdout_fragments=(
                _NATIVE_STALENESS_LABEL,
                "- stg_orders_a",
                "- stg_orders_b",
            ),
            unexpected_exact_stdout_fragments=(
                "table    stg_orders_a",
                "table    stg_orders_b",
            ),
            expected_repair_stdout_fragments=(
                "Plan ready (4 selected)",
                "table     stg_orders_a",
                "table     stg_orders_b",
            ),
            unexpected_repair_stdout_fragments=(_NATIVE_STALENESS_LABEL,),
            expected_rows_after_baseline=((1, 1.0),),
            expected_rows_after_exact_commands=(((1, 1.0),),),
            expected_rows_after_repair=((1, 1.25),),
            database_relative_path=_NATIVE_DATABASE_PATH,
            fact_rows_query=_NATIVE_FACT_ROWS_QUERY,
            notes="The branch-complete traversal must not drop either diamond intermediate.",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_exact_selection_when_upstream_changed_then_preserves_staleness_contract(
    test_case: SelectionStalenessEngineE2ETestCase,
    tmp_path: Path,
) -> None:
    assert test_case.expected_rows_after_repair
    assert_selection_staleness_case(tmp_path=tmp_path, test_case=test_case)
