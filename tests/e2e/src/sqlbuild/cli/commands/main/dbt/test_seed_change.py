from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.dbt._test_types import (
    DbtSeedChangeE2ETestCase,
)
from tests.e2e.src.sqlbuild.cli.commands.main.dbt.helpers import (
    add_dbt_seed_change_second_seed,
    append_dbt_seed_change_order,
    drop_dbt_seed_change_relation,
    edit_dbt_seed_change_leaf_sql,
    prepare_dbt_seed_change_project,
    query_dbt_seed_change_revenue_rows,
    run_dbt_seed_change_build,
    run_dbt_seed_change_command,
    set_dbt_seed_change_column_types,
    skip_unless_dbt_is_runnable,
)

pytestmark: pytest.MarkDecorator = pytest.mark.dbt


@pytest.mark.parametrize(
    "test_case",
    [
        DbtSeedChangeE2ETestCase(
            description="closure rebuild incorporates a changed seed and cascades downstream",
            select=("+fct_customer_revenue",),
            expected_stdout_fragments=(
                "Upstream changed",
                "fct_customer_revenue",
                "int_orders",
                "stg_orders",
            ),
            unexpected_stdout_fragments=("Skipping dbt: no dbt work selected.",),
            expected_revenue_rows=((1, 40), (2, 60), (3, 30)),
        )
    ],
    ids=["closure rebuild incorporates a changed seed and cascades downstream"],
)
def test_given_changed_seed_in_closure_when_building_then_cascades_and_updates_data(
    test_case: DbtSeedChangeE2ETestCase,
    tmp_path: Path,
) -> None:
    skip_unless_dbt_is_runnable()
    project_dir: Path = prepare_dbt_seed_change_project(tmp_path=tmp_path)
    baseline: subprocess.CompletedProcess[str] = run_dbt_seed_change_build(
        project_dir=project_dir, select="+fct_customer_revenue"
    )
    assert baseline.returncode == 0, baseline.stdout + baseline.stderr
    assert query_dbt_seed_change_revenue_rows(project_dir=project_dir) == [
        (1, 40),
        (2, 20),
        (3, 30),
    ]

    append_dbt_seed_change_order(project_dir=project_dir, order_id=105, customer_id=2, amount=40)

    result: subprocess.CompletedProcess[str] = run_dbt_seed_change_build(
        project_dir=project_dir, select=test_case.select[0]
    )

    assert result.returncode == 0, result.stdout + result.stderr
    fragment: str
    for fragment in test_case.expected_stdout_fragments:
        assert fragment in result.stdout
    unexpected: str
    for unexpected in test_case.unexpected_stdout_fragments:
        assert unexpected not in result.stdout
    assert query_dbt_seed_change_revenue_rows(project_dir=project_dir) == list(
        test_case.expected_revenue_rows
    )


@pytest.mark.parametrize(
    "test_case",
    [
        DbtSeedChangeE2ETestCase(
            description="rebuilt seed closure is current on an immediate second build",
            select=("+fct_customer_revenue",),
            expected_stdout_fragments=(
                "planned models: 0 run, 4 current",
                "Skipping dbt: no dbt work selected.",
            ),
            unexpected_stdout_fragments=("Upstream changed",),
            expected_revenue_rows=((1, 40), (2, 20), (3, 30)),
        )
    ],
    ids=["rebuilt seed closure is current on an immediate second build"],
)
def test_given_built_seed_closure_when_rebuilding_then_no_op_proves_identity_round_trip(
    test_case: DbtSeedChangeE2ETestCase,
    tmp_path: Path,
) -> None:
    skip_unless_dbt_is_runnable()
    project_dir: Path = prepare_dbt_seed_change_project(tmp_path=tmp_path)
    first: subprocess.CompletedProcess[str] = run_dbt_seed_change_build(
        project_dir=project_dir, select="+fct_customer_revenue"
    )
    assert first.returncode == 0, first.stdout + first.stderr

    result: subprocess.CompletedProcess[str] = run_dbt_seed_change_build(
        project_dir=project_dir, select=test_case.select[0]
    )

    assert result.returncode == 0, result.stdout + result.stderr
    fragment: str
    for fragment in test_case.expected_stdout_fragments:
        assert fragment in result.stdout
    unexpected: str
    for unexpected in test_case.unexpected_stdout_fragments:
        assert unexpected not in result.stdout
    assert query_dbt_seed_change_revenue_rows(project_dir=project_dir) == list(
        test_case.expected_revenue_rows
    )


@pytest.mark.parametrize(
    "test_case",
    [
        DbtSeedChangeE2ETestCase(
            description="changed seed outside selection leaves leaf current with a stale warning",
            select=("fct_customer_revenue",),
            expected_stdout_fragments=(
                "planned models: 0 run, 1 current",
                "Skipping dbt: no dbt work selected.",
                "Warnings (1)",
                "- raw_orders",
            ),
            unexpected_stdout_fragments=(
                "Upstream changed",
                "stg_orders",
                "dbt execution",
            ),
            expected_revenue_rows=((1, 40), (2, 20), (3, 30)),
        )
    ],
    ids=["changed seed outside selection leaves leaf current with a stale warning"],
)
def test_given_changed_seed_out_of_selection_when_building_leaf_then_no_op_with_warning(
    test_case: DbtSeedChangeE2ETestCase,
    tmp_path: Path,
) -> None:
    skip_unless_dbt_is_runnable()
    project_dir: Path = prepare_dbt_seed_change_project(tmp_path=tmp_path)
    baseline: subprocess.CompletedProcess[str] = run_dbt_seed_change_build(
        project_dir=project_dir, select="+fct_customer_revenue"
    )
    assert baseline.returncode == 0, baseline.stdout + baseline.stderr

    append_dbt_seed_change_order(project_dir=project_dir, order_id=106, customer_id=1, amount=11)

    result: subprocess.CompletedProcess[str] = run_dbt_seed_change_build(
        project_dir=project_dir, select=test_case.select[0]
    )

    assert result.returncode == 0, result.stdout + result.stderr
    fragment: str
    for fragment in test_case.expected_stdout_fragments:
        assert fragment in result.stdout
    unexpected: str
    for unexpected in test_case.unexpected_stdout_fragments:
        assert unexpected not in result.stdout
    assert query_dbt_seed_change_revenue_rows(project_dir=project_dir) == list(
        test_case.expected_revenue_rows
    )


@pytest.mark.parametrize(
    "test_case",
    [
        DbtSeedChangeE2ETestCase(
            description="leaf own-change runs while an unselected changed seed still warns",
            select=("fct_customer_revenue",),
            expected_stdout_fragments=(
                "planned models: 1 run, 0 current",
                "fct_customer_revenue",
                "Warnings (1)",
                "- raw_orders",
            ),
            unexpected_stdout_fragments=("Upstream changed",),
            expected_revenue_rows=((1, 40), (2, 20), (3, 30)),
        )
    ],
    ids=["leaf own-change runs while an unselected changed seed still warns"],
)
def test_given_leaf_change_and_out_of_selection_seed_when_building_then_runs_and_warns(
    test_case: DbtSeedChangeE2ETestCase,
    tmp_path: Path,
) -> None:
    skip_unless_dbt_is_runnable()
    project_dir: Path = prepare_dbt_seed_change_project(tmp_path=tmp_path)
    baseline: subprocess.CompletedProcess[str] = run_dbt_seed_change_build(
        project_dir=project_dir, select="+fct_customer_revenue"
    )
    assert baseline.returncode == 0, baseline.stdout + baseline.stderr

    append_dbt_seed_change_order(project_dir=project_dir, order_id=107, customer_id=2, amount=5)
    edit_dbt_seed_change_leaf_sql(project_dir=project_dir)

    result: subprocess.CompletedProcess[str] = run_dbt_seed_change_build(
        project_dir=project_dir, select=test_case.select[0]
    )

    assert result.returncode == 0, result.stdout + result.stderr
    fragment: str
    for fragment in test_case.expected_stdout_fragments:
        assert fragment in result.stdout
    unexpected: str
    for unexpected in test_case.unexpected_stdout_fragments:
        assert unexpected not in result.stdout
    assert query_dbt_seed_change_revenue_rows(project_dir=project_dir) == list(
        test_case.expected_revenue_rows
    )


@pytest.mark.parametrize(
    "test_case",
    [
        DbtSeedChangeE2ETestCase(
            description="config-only seed column_types change is detected and cascades",
            select=("+fct_customer_revenue",),
            expected_stdout_fragments=("Upstream changed", "fct_customer_revenue"),
            unexpected_stdout_fragments=("Skipping dbt: no dbt work selected.",),
            expected_revenue_rows=((1, 40), (2, 20), (3, 30)),
        )
    ],
    ids=["config-only seed column_types change is detected and cascades"],
)
def test_given_config_only_seed_change_when_building_then_seed_is_detected_as_changed(
    test_case: DbtSeedChangeE2ETestCase,
    tmp_path: Path,
) -> None:
    skip_unless_dbt_is_runnable()
    project_dir: Path = prepare_dbt_seed_change_project(tmp_path=tmp_path)
    baseline: subprocess.CompletedProcess[str] = run_dbt_seed_change_build(
        project_dir=project_dir, select="+fct_customer_revenue"
    )
    assert baseline.returncode == 0, baseline.stdout + baseline.stderr

    set_dbt_seed_change_column_types(project_dir=project_dir)

    result: subprocess.CompletedProcess[str] = run_dbt_seed_change_build(
        project_dir=project_dir, select=test_case.select[0]
    )

    assert result.returncode == 0, result.stdout + result.stderr
    fragment: str
    for fragment in test_case.expected_stdout_fragments:
        assert fragment in result.stdout
    unexpected: str
    for unexpected in test_case.unexpected_stdout_fragments:
        assert unexpected not in result.stdout
    assert query_dbt_seed_change_revenue_rows(project_dir=project_dir) == list(
        test_case.expected_revenue_rows
    )


@pytest.mark.parametrize(
    "test_case",
    [
        DbtSeedChangeE2ETestCase(
            description="dropped seed relation reloads the seed and rebuilds dependents",
            select=("+fct_customer_revenue",),
            expected_stdout_fragments=(
                "Seeds (1, changed)",
                "seed      raw_orders",
                "model     stg_orders",
                "model     fct_customer_revenue",
                "Seeds pruned (1)",
                "raw_customers",
            ),
            unexpected_stdout_fragments=("Skipping dbt: no dbt work selected.",),
            expected_revenue_rows=((1, 40), (2, 20), (3, 30)),
        )
    ],
    ids=["dropped seed relation reloads the seed and rebuilds dependents"],
)
def test_given_dropped_seed_relation_when_building_then_reloads_and_rebuilds(
    test_case: DbtSeedChangeE2ETestCase,
    tmp_path: Path,
) -> None:
    skip_unless_dbt_is_runnable()
    project_dir: Path = prepare_dbt_seed_change_project(tmp_path=tmp_path)
    baseline: subprocess.CompletedProcess[str] = run_dbt_seed_change_build(
        project_dir=project_dir, select="+fct_customer_revenue"
    )
    assert baseline.returncode == 0, baseline.stdout + baseline.stderr

    drop_dbt_seed_change_relation(project_dir=project_dir, relation="raw_orders")

    result: subprocess.CompletedProcess[str] = run_dbt_seed_change_build(
        project_dir=project_dir, select=test_case.select[0]
    )

    assert result.returncode == 0, result.stdout + result.stderr
    fragment: str
    for fragment in test_case.expected_stdout_fragments:
        assert fragment in result.stdout
    unexpected: str
    for unexpected in test_case.unexpected_stdout_fragments:
        assert unexpected not in result.stdout
    assert query_dbt_seed_change_revenue_rows(project_dir=project_dir) == list(
        test_case.expected_revenue_rows
    )


@pytest.mark.parametrize(
    "test_case",
    [
        DbtSeedChangeE2ETestCase(
            description="config-only seed change is current on an immediate second build",
            select=("+fct_customer_revenue",),
            expected_stdout_fragments=(
                "planned models: 0 run, 4 current",
                "Skipping dbt: no dbt work selected.",
            ),
            unexpected_stdout_fragments=("Upstream changed",),
            expected_revenue_rows=((1, 40), (2, 20), (3, 30)),
        )
    ],
    ids=["config-only seed change is current on an immediate second build"],
)
def test_given_config_only_seed_change_when_rebuilding_then_no_op_round_trips(
    test_case: DbtSeedChangeE2ETestCase,
    tmp_path: Path,
) -> None:
    skip_unless_dbt_is_runnable()
    project_dir: Path = prepare_dbt_seed_change_project(tmp_path=tmp_path)
    baseline: subprocess.CompletedProcess[str] = run_dbt_seed_change_build(
        project_dir=project_dir, select="+fct_customer_revenue"
    )
    assert baseline.returncode == 0, baseline.stdout + baseline.stderr
    set_dbt_seed_change_column_types(project_dir=project_dir)
    changed: subprocess.CompletedProcess[str] = run_dbt_seed_change_build(
        project_dir=project_dir, select="+fct_customer_revenue"
    )
    assert changed.returncode == 0, changed.stdout + changed.stderr

    result: subprocess.CompletedProcess[str] = run_dbt_seed_change_build(
        project_dir=project_dir, select=test_case.select[0]
    )

    assert result.returncode == 0, result.stdout + result.stderr
    fragment: str
    for fragment in test_case.expected_stdout_fragments:
        assert fragment in result.stdout
    unexpected: str
    for unexpected in test_case.unexpected_stdout_fragments:
        assert unexpected not in result.stdout
    assert query_dbt_seed_change_revenue_rows(project_dir=project_dir) == list(
        test_case.expected_revenue_rows
    )


@pytest.mark.parametrize(
    "test_case",
    [
        DbtSeedChangeE2ETestCase(
            description="changing one seed cascades only into its own branch",
            select=("+fct_customer_revenue",),
            expected_stdout_fragments=("Upstream changed", "fct_customer_revenue"),
            unexpected_stdout_fragments=("dim_regions",),
            expected_revenue_rows=((1, 40), (2, 60), (3, 30)),
        )
    ],
    ids=["changing one seed cascades only into its own branch"],
)
def test_given_two_seed_branches_when_one_seed_changes_then_only_its_branch_cascades(
    test_case: DbtSeedChangeE2ETestCase,
    tmp_path: Path,
) -> None:
    skip_unless_dbt_is_runnable()
    project_dir: Path = prepare_dbt_seed_change_project(tmp_path=tmp_path)
    add_dbt_seed_change_second_seed(project_dir=project_dir)
    baseline: subprocess.CompletedProcess[str] = run_dbt_seed_change_command(
        project_dir=project_dir,
        command=(
            "--no-color",
            "dbt",
            "build",
            "--select",
            "+fct_customer_revenue",
            "+dim_regions",
        ),
    )
    assert baseline.returncode == 0, baseline.stdout + baseline.stderr

    append_dbt_seed_change_order(project_dir=project_dir, order_id=105, customer_id=2, amount=40)

    result: subprocess.CompletedProcess[str] = run_dbt_seed_change_build(
        project_dir=project_dir, select=test_case.select[0]
    )

    assert result.returncode == 0, result.stdout + result.stderr
    fragment: str
    for fragment in test_case.expected_stdout_fragments:
        assert fragment in result.stdout
    unexpected: str
    for unexpected in test_case.unexpected_stdout_fragments:
        assert unexpected not in result.stdout
    assert query_dbt_seed_change_revenue_rows(project_dir=project_dir) == list(
        test_case.expected_revenue_rows
    )


@pytest.mark.parametrize(
    "test_case",
    [
        DbtSeedChangeE2ETestCase(
            description="dbt run warns about an out-of-selection changed seed",
            select=("fct_customer_revenue",),
            expected_stdout_fragments=(
                "planned models: 0 run, 1 current",
                "Warnings (1)",
                "- raw_orders",
            ),
            unexpected_stdout_fragments=("Upstream changed",),
            expected_revenue_rows=((1, 40), (2, 20), (3, 30)),
        )
    ],
    ids=["dbt run warns about an out-of-selection changed seed"],
)
def test_given_out_of_selection_seed_change_when_running_then_warns(
    test_case: DbtSeedChangeE2ETestCase,
    tmp_path: Path,
) -> None:
    skip_unless_dbt_is_runnable()
    project_dir: Path = prepare_dbt_seed_change_project(tmp_path=tmp_path)
    baseline: subprocess.CompletedProcess[str] = run_dbt_seed_change_build(
        project_dir=project_dir, select="+fct_customer_revenue"
    )
    assert baseline.returncode == 0, baseline.stdout + baseline.stderr

    append_dbt_seed_change_order(project_dir=project_dir, order_id=106, customer_id=1, amount=11)

    result: subprocess.CompletedProcess[str] = run_dbt_seed_change_command(
        project_dir=project_dir,
        command=("--no-color", "dbt", "run", "--select", test_case.select[0]),
    )

    assert result.returncode == 0, result.stdout + result.stderr
    fragment: str
    for fragment in test_case.expected_stdout_fragments:
        assert fragment in result.stdout
    unexpected: str
    for unexpected in test_case.unexpected_stdout_fragments:
        assert unexpected not in result.stdout
    assert query_dbt_seed_change_revenue_rows(project_dir=project_dir) == list(
        test_case.expected_revenue_rows
    )
