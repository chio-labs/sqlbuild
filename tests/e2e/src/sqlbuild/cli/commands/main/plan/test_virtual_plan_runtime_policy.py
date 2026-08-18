from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import cast

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.plan._test_types import (
    VirtualPlanE2ETestCase,
    VirtualSourceFreshnessPlanE2ETestCase,
)
from tests.e2e.src.sqlbuild.cli.commands.main.plan.helpers import (
    build_virtual_plan_repo_files,
    prepare_virtual_run_despite_unchanged_project,
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
            description="virtual plan shows config changed root without query diff",
            seed_matching_refs=True,
            command=("--no-color", "plan", "--changes-only"),
            expected_fragments=(
                "Plan ready  2 selected",
                "directly affected (1)  stg_orders",
                "Config changed (1)",
                "stg_orders",
                "config diff:",
                '"materialized": "view"',
                '"materialized": "table"',
                "Upstream changed (1)",
                "fact_orders",
                "cause  stg_orders (config changed)",
            ),
            unexpected_fragments=("Query changed", "query diff:"),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_virtual_plan_with_config_change_when_running_cli_then_it_uses_config_reason(
    test_case: VirtualPlanE2ETestCase,
    tmp_path: Path,
) -> None:
    baseline_project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="virtual_plan_config_baseline",
        repo_files={
            "sqlbuild_project.toml": build_virtual_plan_repo_files(stg_orders_sql="SELECT 1 AS id")[
                "sqlbuild_project.toml"
            ],
            "models/stg_orders.sql": "MODEL (materialized view);\n\nSELECT 1 AS id\n",
            "models/fact_orders.sql": 'MODEL ();\n\nSELECT id FROM __ref("stg_orders")\n',
        },
    )
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="virtual_plan_config_current",
        repo_files={
            "sqlbuild_project.toml": build_virtual_plan_repo_files(stg_orders_sql="SELECT 1 AS id")[
                "sqlbuild_project.toml"
            ],
            "models/stg_orders.sql": "MODEL (materialized table);\n\nSELECT 1 AS id\n",
            "models/fact_orders.sql": 'MODEL ();\n\nSELECT id FROM __ref("stg_orders")\n',
        },
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


@pytest.mark.parametrize(
    "test_case",
    [
        VirtualSourceFreshnessPlanE2ETestCase(
            description="virtual changes-only runs configured table despite unchanged freshness",
            expected_unchanged_fragments=(
                "Plan ready  2 selected",
                "Runs despite unchanged (1)",
            ),
            expected_fragments=(
                "Plan ready  2 selected",
                "Runs despite unchanged (1)",
                "rolling_orders",
                "run_despite_unchanged  30d",
                "Upstream changed (1)",
                "orders_mart",
                "cause  rolling_orders ran despite unchanged inputs",
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_virtual_run_despite_unchanged_when_planning_changes_only_then_selects_downstream(
    test_case: VirtualSourceFreshnessPlanE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_virtual_run_despite_unchanged_project(
        tmp_path=tmp_path,
        project_name="virtual_run_despite_unchanged_plan",
        run_despite_unchanged="30d",
        data_version_sql="CURRENT_TIMESTAMP",
    )
    build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"),
        project_dir=project_dir,
    )
    assert build_result.returncode == 0, build_result.stderr

    unchanged_plan_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "plan"),
        project_dir=project_dir,
    )
    assert unchanged_plan_result.returncode == 0, unchanged_plan_result.stderr
    fragment: str
    for fragment in test_case.expected_unchanged_fragments:
        assert fragment in unchanged_plan_result.stdout, unchanged_plan_result.stdout

    changes_only_plan_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "plan", "--changes-only"),
        project_dir=project_dir,
    )
    assert changes_only_plan_result.returncode == 0, changes_only_plan_result.stderr
    output: str = changes_only_plan_result.stdout
    for fragment in test_case.expected_fragments:
        assert fragment in output, output
    for fragment in test_case.unexpected_fragments:
        assert fragment not in output, output


@pytest.mark.parametrize(
    "test_case",
    [
        VirtualSourceFreshnessPlanE2ETestCase(
            description="virtual changes-only skips expired run_despite_unchanged duration",
            expected_unchanged_fragments=("Plan ready  0 selected",),
            expected_fragments=("Plan ready  0 selected",),
            unexpected_fragments=("Runs despite unchanged", "rolling_orders", "orders_mart"),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_virtual_expired_run_despite_unchanged_when_planning_then_skips_table(
    test_case: VirtualSourceFreshnessPlanE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_virtual_run_despite_unchanged_project(
        tmp_path=tmp_path,
        project_name="virtual_run_despite_unchanged_expired_plan",
        run_despite_unchanged="1d",
        data_version_sql="TIMESTAMP '2026-01-01 00:00:00'",
    )
    build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"),
        project_dir=project_dir,
    )
    assert build_result.returncode == 0, build_result.stderr

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "plan", "--changes-only"),
        project_dir=project_dir,
    )
    assert result.returncode == 0, result.stderr
    fragment: str
    for fragment in test_case.expected_fragments:
        assert fragment in result.stdout, result.stdout
    for fragment in test_case.unexpected_fragments:
        assert fragment not in result.stdout, result.stdout


@pytest.mark.parametrize(
    "test_case",
    [
        VirtualSourceFreshnessPlanE2ETestCase(
            description="virtual changes-only always runs configured unchanged table",
            expected_unchanged_fragments=(),
            expected_fragments=(
                "Plan ready  2 selected",
                "Runs despite unchanged (1)",
                "rolling_orders",
                "run_despite_unchanged  always",
                "orders_mart",
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_virtual_run_despite_unchanged_always_when_planning_then_selects_downstream(
    test_case: VirtualSourceFreshnessPlanE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_virtual_run_despite_unchanged_project(
        tmp_path=tmp_path,
        project_name="virtual_run_despite_unchanged_always_plan",
        run_despite_unchanged="always",
        data_version_sql="TIMESTAMP '2026-01-01 00:00:00'",
    )
    build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"),
        project_dir=project_dir,
    )
    assert build_result.returncode == 0, build_result.stderr

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "plan", "--changes-only"),
        project_dir=project_dir,
    )
    assert result.returncode == 0, result.stderr
    fragment: str
    for fragment in test_case.expected_fragments:
        assert fragment in result.stdout, result.stdout


@pytest.mark.parametrize(
    "test_case",
    [
        VirtualSourceFreshnessPlanE2ETestCase(
            description="virtual JSON exposes run_despite_unchanged metadata",
            expected_unchanged_fragments=(),
            expected_fragments=("rolling_orders", "30d", "raw_orders"),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_virtual_run_despite_unchanged_when_planning_json_then_outputs_metadata(
    test_case: VirtualSourceFreshnessPlanE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_virtual_run_despite_unchanged_project(
        tmp_path=tmp_path,
        project_name="virtual_run_despite_unchanged_json_plan",
        run_despite_unchanged="30d",
        data_version_sql="CURRENT_TIMESTAMP",
    )
    build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"),
        project_dir=project_dir,
    )
    assert build_result.returncode == 0, build_result.stderr

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "plan", "--json", "--changes-only"),
        project_dir=project_dir,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    payload: dict[str, object] = cast(dict[str, object], json.loads(result.stdout))
    models: list[dict[str, object]] = cast(list[dict[str, object]], payload["models"])
    models_by_name: dict[str, tuple[dict[str, object], ...]] = {
        str(model["name"]): (model,) for model in models
    }
    assert len(models_by_name) == len(models)
    root_model: dict[str, object] = next(iter(models_by_name.get("rolling_orders", ())))
    run_metadata: dict[str, object] = cast(dict[str, object], root_model["run_despite_unchanged"])

    assert root_model["name"] == test_case.expected_fragments[0]
    assert payload["selected_count"] == 2
    assert root_model["reason"] == "run_despite_unchanged"
    assert run_metadata["mode"] == "duration"
    assert run_metadata["duration"] == test_case.expected_fragments[1]
    assert run_metadata["newest_source_name"] == test_case.expected_fragments[2]
    assert isinstance(run_metadata["newest_source_data_age_seconds"], int)


@pytest.mark.parametrize(
    "test_case",
    [
        VirtualSourceFreshnessPlanE2ETestCase(
            description="virtual scoped runtime stale root leaves downstream remaining stale",
            expected_unchanged_fragments=(),
            expected_fragments=(
                "Plan ready  1 selected",
                "Runs despite unchanged (1)",
                "rolling_orders",
                "outside this plan (1)  orders_mart",
            ),
            unexpected_fragments=("Upstream changed (1)",),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_virtual_scoped_run_despite_unchanged_when_planning_then_downstream_remains_stale(
    test_case: VirtualSourceFreshnessPlanE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_virtual_run_despite_unchanged_project(
        tmp_path=tmp_path,
        project_name="virtual_run_despite_unchanged_scoped_plan",
        run_despite_unchanged="30d",
        data_version_sql="CURRENT_TIMESTAMP",
    )
    build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"),
        project_dir=project_dir,
    )
    assert build_result.returncode == 0, build_result.stderr

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "plan", "--select", "rolling_orders", "--changes-only"),
        project_dir=project_dir,
    )
    assert result.returncode == 0, result.stderr
    fragment: str
    for fragment in test_case.expected_fragments:
        assert fragment in result.stdout, result.stdout
    for fragment in test_case.unexpected_fragments:
        assert fragment not in result.stdout, result.stdout


@pytest.mark.parametrize(
    "test_case",
    (
        VirtualSourceFreshnessPlanE2ETestCase(
            description="virtual duration mode fails without source freshness",
            expected_unchanged_fragments=(),
            expected_fragments=("cannot determine upstream source freshness age",),
            project_suffix="missing",
            data_version_sql="TIMESTAMP '2026-06-01 00:00:00'",
            include_freshness=False,
            source_freshness_type="timestamp",
            warehouse_column_type="TIMESTAMP",
        ),
        VirtualSourceFreshnessPlanE2ETestCase(
            description="virtual duration mode fails with integer source freshness",
            expected_unchanged_fragments=(),
            expected_fragments=("requires timestamp source freshness",),
            project_suffix="integer",
            data_version_sql="1",
            include_freshness=True,
            source_freshness_type="integer",
            warehouse_column_type="INTEGER",
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_virtual_duration_without_timestamp_freshness_when_planning_then_fails(
    test_case: VirtualSourceFreshnessPlanE2ETestCase,
    tmp_path: Path,
) -> None:
    assert test_case.project_suffix is not None
    assert test_case.data_version_sql is not None
    project_dir: Path = prepare_virtual_run_despite_unchanged_project(
        tmp_path=tmp_path,
        project_name=f"virtual_run_despite_unchanged_error_{test_case.project_suffix}",
        run_despite_unchanged="30d",
        data_version_sql=test_case.data_version_sql,
        include_freshness=test_case.include_freshness,
        source_freshness_type=test_case.source_freshness_type,
        warehouse_column_type=test_case.warehouse_column_type,
    )

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "plan", "--changes-only"),
        project_dir=project_dir,
    )
    assert result.returncode != 0, result.stdout + result.stderr
    fragment: str
    for fragment in test_case.expected_fragments:
        assert fragment in result.stdout + result.stderr, result.stdout + result.stderr
