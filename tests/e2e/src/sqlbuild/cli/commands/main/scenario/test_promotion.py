"""E2E tests for scenario table promotion matching build configuration."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.scenario._test_types import (
    ScenarioPromotionE2ETestCase,
)
from tests.e2e.src.sqlbuild.cli.commands.main.scenario.helpers import (
    build_promotion_project_files,
    list_scenario_relation_names,
)
from tests.e2e.src.sqlbuild.cli.commands.shared.helpers import (
    execute_duckdb,
    prepare_inline_project,
    run_sqb,
)

_MATCHING_COLUMNS: str = (
    "  columns (\n    total_amount (type BIGINT),\n    order_count (type BIGINT),\n  ),\n"
)
_ENFORCED_DEFAULTS: str = 'contract = "enforced"\n'


@pytest.mark.parametrize(
    "test_case",
    (
        ScenarioPromotionE2ETestCase(
            description="project enforced contract runs the contract check and expectations",
            defaults_config=_ENFORCED_DEFAULTS,
            settings_config="",
            model_columns=_MATCHING_COLUMNS,
            expected_exit_code=0,
            expected_stdout_fragments=(
                "expect    expected order_totals",
                "PASS=1  FAIL=0  TOTAL=1",
            ),
            expect_staged_promotion=True,
        ),
        ScenarioPromotionE2ETestCase(
            description="explicit immediate setting is honoured without a contract",
            defaults_config="",
            settings_config='[settings]\ntable_promotion_mode = "immediate"\n',
            model_columns="",
            expected_exit_code=0,
            expected_stdout_fragments=("PASS=1  FAIL=0  TOTAL=1",),
            expect_staged_promotion=False,
        ),
        ScenarioPromotionE2ETestCase(
            description="explicit staged setting enables declared type enforcement",
            defaults_config="",
            settings_config='[settings]\ntable_promotion_mode = "staged"\n',
            model_columns=_MATCHING_COLUMNS,
            expected_exit_code=0,
            expected_stdout_fragments=("PASS=1  FAIL=0  TOTAL=1",),
            expect_staged_promotion=True,
        ),
        ScenarioPromotionE2ETestCase(
            description="runtime contract failure is reported and staging is cleaned up",
            defaults_config=_ENFORCED_DEFAULTS,
            settings_config="",
            model_columns=_MATCHING_COLUMNS.replace(
                "  ),\n", "    discount_amount (type BIGINT),\n  ),\n"
            ),
            expected_exit_code=1,
            expected_stdout_fragments=(
                "error[K008]",
                "runtime contract missing columns: discount_amount",
                "PASS=0  FAIL=1  TOTAL=1",
            ),
            expect_staged_promotion=True,
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_promotion_configuration_when_running_scenario_then_matches_build_promotion(
    test_case: ScenarioPromotionE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="scenario_promotion",
        repo_files=build_promotion_project_files(test_case),
    )

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "scenario", "test"),
        project_dir=project_dir,
    )

    output: str = result.stdout + result.stderr
    assert result.returncode == test_case.expected_exit_code, output
    for fragment in test_case.expected_stdout_fragments:
        assert fragment in result.stdout, output
    for fragment in test_case.unexpected_stdout_fragments:
        assert fragment not in output
    model_sql: str = (
        project_dir / "target/run/scenarios/order_totals_pass/models/order_totals.sql"
    ).read_text(encoding="utf-8")
    assert ("__staging" in model_sql) is test_case.expect_staged_promotion, model_sql
    assert list_scenario_relation_names(db_path=project_dir / "scenario_promotion.duckdb") == ()


@pytest.mark.parametrize(
    "test_case",
    (
        ScenarioPromotionE2ETestCase(
            description="enforced contract with immediate promotion fails like build",
            defaults_config=_ENFORCED_DEFAULTS,
            settings_config='[settings]\ntable_promotion_mode = "immediate"\n',
            model_columns=_MATCHING_COLUMNS,
            expected_exit_code=1,
            expected_stdout_fragments=(
                "[K011]",
                "contract enforced requires staged table promotion",
            ),
            expect_staged_promotion=False,
            unexpected_stdout_fragments=(),
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_enforced_contract_and_immediate_promotion_when_running_then_matches_build_k011(
    test_case: ScenarioPromotionE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="scenario_promotion",
        repo_files=build_promotion_project_files(test_case),
    )
    execute_duckdb(
        db_path=project_dir / "scenario_promotion.duckdb",
        sql="CREATE TABLE main.raw_orders AS SELECT 1 AS id, 10 AS amount",
    )

    build: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"), project_dir=project_dir
    )
    scenario: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "scenario", "test"), project_dir=project_dir
    )

    assert build.returncode == test_case.expected_exit_code, build.stdout + build.stderr
    assert scenario.returncode == test_case.expected_exit_code, scenario.stdout + scenario.stderr
    for fragment in test_case.expected_stdout_fragments:
        assert fragment in build.stdout + build.stderr
        assert fragment in scenario.stdout
    assert list_scenario_relation_names(db_path=project_dir / "scenario_promotion.duckdb") == ()


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
