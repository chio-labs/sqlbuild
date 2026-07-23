from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.plan._test_types import (
    VirtualPlanE2ETestCase,
    VirtualPlanJsonE2ETestCase,
    VirtualPlanSelectionGuardE2ETestCase,
)
from tests.e2e.src.sqlbuild.cli.commands.main.plan.helpers import (
    build_virtual_plan_repo_files,
    seed_matching_virtual_refs,
)
from tests.e2e.src.sqlbuild.cli.commands.shared.helpers import (
    prepare_inline_project,
    run_sqb,
)


@pytest.mark.parametrize(
    "test_case",
    [
        VirtualPlanE2ETestCase(
            description="virtual plan selects nothing when all bound refs match expected hashes",
            seed_matching_refs=True,
            command=("--no-color", "plan", "--changes-only"),
            expected_fragments=(
                "Plan ready (0 selected)",
                "Virtual environment",
                "name: dev",
                "status: finalized",
                "stale models: 0",
            ),
            unexpected_fragments=("First run", "fact_orders", "dim_customers", "stg_orders"),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_virtual_plan_with_matching_refs_when_running_cli_then_it_selects_nothing(
    test_case: VirtualPlanE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="virtual_plan_project",
        repo_files=build_virtual_plan_repo_files(stg_orders_sql="SELECT 1 AS id"),
    )

    init_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("state", "init"),
        project_dir=project_dir,
    )
    assert init_result.returncode == 0, init_result.stderr
    seed_matching_virtual_refs(project_dir=project_dir)

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.command,
        project_dir=project_dir,
    )

    assert result.returncode == 0, result.stderr
    output: str = result.stdout
    fragment: str
    for fragment in test_case.expected_fragments:
        assert fragment in output, output
    for fragment in test_case.unexpected_fragments:
        assert fragment not in output, output


@pytest.mark.parametrize(
    "test_case",
    [
        VirtualPlanE2ETestCase(
            description="virtual plan with multiple stale roots excludes unaffected branches",
            seed_matching_refs=True,
            command=("--no-color", "plan", "--changes-only"),
            expected_fragments=(
                "Plan ready (3 selected)",
                "stale roots: 2",
                "stale root set: dim_customers, stg_orders",
                "stale models: 3",
                "stale model set: dim_customers, fact_orders, stg_orders",
                "Query changed (2)",
                "stg_orders",
                "dim_customers",
                "Upstream changed (1)",
                "fact_orders",
            ),
            unexpected_fragments=("static_model",),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_virtual_plan_with_multiple_stale_roots_when_running_cli_then_it_excludes_unaffected(
    test_case: VirtualPlanE2ETestCase,
    tmp_path: Path,
) -> None:
    baseline_project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="virtual_plan_multi_root_baseline",
        repo_files=build_virtual_plan_repo_files(
            stg_orders_sql="SELECT 1 AS id",
            dim_customers_sql="SELECT 1 AS customer_id",
        )
        | {"models/static_model.sql": "MODEL ();\n\nSELECT 99 AS static_value\n"},
    )
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="virtual_plan_multi_root",
        repo_files=build_virtual_plan_repo_files(
            stg_orders_sql="SELECT 2 AS id",
            dim_customers_sql="SELECT 2 AS customer_id",
        )
        | {"models/static_model.sql": "MODEL ();\n\nSELECT 99 AS static_value\n"},
    )

    init_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("state", "init"),
        project_dir=project_dir,
    )
    assert init_result.returncode == 0, init_result.stderr
    seed_matching_virtual_refs(
        project_dir=project_dir,
        source_project_dir=baseline_project_dir,
    )

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.command,
        project_dir=project_dir,
    )

    assert result.returncode == 0, result.stderr
    output: str = result.stdout
    fragment: str
    for fragment in test_case.expected_fragments:
        assert fragment in output, output
    for fragment in test_case.unexpected_fragments:
        assert fragment not in output, output


@pytest.mark.parametrize(
    "test_case",
    [
        VirtualPlanE2ETestCase(
            description="virtual plan explicit select bypasses stale-driven selection",
            seed_matching_refs=True,
            command=("--no-color", "plan", "--select", "dim_customers"),
            expected_fragments=(
                "Plan ready (1 selected)",
                "Virtual environment",
                "stale roots: 1",
                "stale root set: stg_orders",
                "dim_customers",
            ),
            unexpected_fragments=("Upstream changed (1)",),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_virtual_plan_with_explicit_select_when_running_cli_then_it_bypasses_default_scope(
    test_case: VirtualPlanE2ETestCase,
    tmp_path: Path,
) -> None:
    baseline_project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="virtual_plan_select_baseline",
        repo_files=build_virtual_plan_repo_files(stg_orders_sql="SELECT 1 AS id"),
    )
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="virtual_plan_select_current",
        repo_files=build_virtual_plan_repo_files(stg_orders_sql="SELECT 2 AS id"),
    )

    init_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("state", "init"),
        project_dir=project_dir,
    )
    assert init_result.returncode == 0, init_result.stderr
    seed_matching_virtual_refs(
        project_dir=project_dir,
        source_project_dir=baseline_project_dir,
    )

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.command,
        project_dir=project_dir,
    )

    assert result.returncode == 0, result.stderr
    output: str = result.stdout
    fragment: str
    for fragment in test_case.expected_fragments:
        assert fragment in output, output
    for fragment in test_case.unexpected_fragments:
        assert fragment not in output, output


@pytest.mark.parametrize(
    "test_case",
    [
        VirtualPlanSelectionGuardE2ETestCase(
            description="selected downstream with stale upstream blocks",
            command=("--no-color", "plan", "--select", "fact_orders", "--changes-only"),
            expected_exit_code=1,
            expected_fragments=(
                "missing stale required upstream models: stg_orders",
                "--include-stale-upstreams",
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_virtual_plan_selected_downstream_with_stale_upstream_when_running_then_it_blocks(
    test_case: VirtualPlanSelectionGuardE2ETestCase,
    tmp_path: Path,
) -> None:
    baseline_project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="virtual_plan_guard_baseline",
        repo_files=build_virtual_plan_repo_files(stg_orders_sql="SELECT 1 AS id"),
    )
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="virtual_plan_guard_current",
        repo_files=build_virtual_plan_repo_files(stg_orders_sql="SELECT 2 AS id"),
    )

    init_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("state", "init"),
        project_dir=project_dir,
    )
    assert init_result.returncode == 0, init_result.stderr
    seed_matching_virtual_refs(
        project_dir=project_dir,
        source_project_dir=baseline_project_dir,
    )

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.command,
        project_dir=project_dir,
    )

    assert result.returncode == test_case.expected_exit_code
    output: str = result.stdout + result.stderr
    fragment: str
    for fragment in test_case.expected_fragments:
        assert fragment in output


@pytest.mark.parametrize(
    "test_case",
    [
        VirtualPlanSelectionGuardE2ETestCase(
            description="include stale upstreams with default pruning narrows scope",
            command=(
                "--no-color",
                "plan",
                "--select",
                "fact_orders",
                "--select",
                "dim_customers",
                "--include-stale-upstreams",
                "--changes-only",
            ),
            expected_exit_code=0,
            expected_fragments=("Plan ready (2 selected)", "stg_orders", "fact_orders"),
            unexpected_fragments=("dim_customers",),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_virtual_plan_include_stale_upstreams_when_running_then_it_expands_minimally(
    test_case: VirtualPlanSelectionGuardE2ETestCase,
    tmp_path: Path,
) -> None:
    baseline_project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="virtual_plan_include_baseline",
        repo_files=build_virtual_plan_repo_files(stg_orders_sql="SELECT 1 AS id"),
    )
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="virtual_plan_include_current",
        repo_files=build_virtual_plan_repo_files(stg_orders_sql="SELECT 2 AS id"),
    )

    init_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("state", "init"),
        project_dir=project_dir,
    )
    assert init_result.returncode == 0, init_result.stderr
    seed_matching_virtual_refs(
        project_dir=project_dir,
        source_project_dir=baseline_project_dir,
    )

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.command,
        project_dir=project_dir,
    )

    assert result.returncode == test_case.expected_exit_code, result.stderr
    output: str = result.stdout
    fragment: str
    for fragment in test_case.expected_fragments:
        assert fragment in output
    for fragment in test_case.unexpected_fragments:
        assert fragment not in output


@pytest.mark.parametrize(
    "test_case",
    [
        VirtualPlanJsonE2ETestCase(
            description="virtual plan json includes metadata fields",
            expected_json_fragments=(
                '"metadata"',
                '"virtual_environment_name": "dev"',
                '"virtual_environment_status": "working"',
                '"virtual_stale_model_names"',
                '"virtual_stale_root_names"',
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_virtual_plan_json_when_running_cli_then_it_includes_virtual_metadata(
    test_case: VirtualPlanJsonE2ETestCase,
    tmp_path: Path,
) -> None:
    baseline_project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="virtual_plan_json_baseline",
        repo_files=build_virtual_plan_repo_files(stg_orders_sql="SELECT 1 AS id"),
    )
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="virtual_plan_json_current",
        repo_files=build_virtual_plan_repo_files(stg_orders_sql="SELECT 2 AS id"),
    )

    init_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("state", "init"),
        project_dir=project_dir,
    )
    assert init_result.returncode == 0, init_result.stderr
    seed_matching_virtual_refs(
        project_dir=project_dir,
        source_project_dir=baseline_project_dir,
    )

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=("plan", "--json"),
        project_dir=project_dir,
    )

    assert result.returncode == 0, result.stderr
    output: str = result.stdout
    parsed: dict[str, object] = json.loads(output)
    assert "metadata" in parsed
    fragment: str
    for fragment in test_case.expected_json_fragments:
        assert fragment in output, output
