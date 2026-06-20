from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.dbt._test_types import DbtScenarioCliTestCase
from tests.e2e.src.sqlbuild.cli.commands.main.dbt.helpers import (
    compile_dbt_interop_manifest,
    install_dbt_interop_packages,
    prepare_dbt_interop_project,
    seed_real_dbt_source_orders,
    skip_unless_dbt_is_runnable,
    write_chained_dbt_scenario_targeting_dbt_model,
    write_dbt_scenario_targeting_dbt_model,
    write_failing_assertion_dbt_scenario,
    write_failing_expected_dbt_scenario,
    write_qualified_source_dbt_scenario,
    write_real_source_fixture_dbt_scenario,
    write_ref_boundary_dbt_scenario,
    write_seed_dbt_scenario_targeting_dbt_model,
    write_snapshot_boundary_dbt_scenario,
    write_spanning_sqlbuild_dbt_ref_scenario,
)
from tests.e2e.src.sqlbuild.cli.commands.main.shared.helpers import run_sqb, table_exists

pytestmark: pytest.MarkDecorator = pytest.mark.dbt


@pytest.mark.parametrize(
    "test_case",
    [
        DbtScenarioCliTestCase(
            description="scenario runs with mocked package-qualified dbt refs",
            command=("--no-color", "scenario", "test", "downstream_orders"),
            expected_stdout_fragments=(
                "Scenario (1 selected)",
                "downstream_orders",
                "expect    expected downstream_orders",
                "expect    assertion downstream_joined",
                "PASS=1  FAIL=0  TOTAL=1",
            ),
            expected_absent_relations=("fact_orders",),
        )
    ],
    ids=["scenario runs with mocked package-qualified dbt refs"],
)
def test_given_dbt_interop_project_when_running_scenario_then_mocks_dbt_refs(
    test_case: DbtScenarioCliTestCase,
    tmp_path: Path,
) -> None:
    skip_unless_dbt_is_runnable()
    project_dir: Path = prepare_dbt_interop_project(tmp_path=tmp_path)
    setup_result: subprocess.CompletedProcess[str] = compile_dbt_interop_manifest(
        project_dir=project_dir
    )
    assert setup_result.returncode == 0, setup_result.stdout + setup_result.stderr

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.command,
        project_dir=project_dir,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    expected_stdout_fragment: str
    for expected_stdout_fragment in test_case.expected_stdout_fragments:
        assert expected_stdout_fragment in result.stdout
    db_path: Path = project_dir / "dbt_interop.duckdb"
    absent_relation: str
    for absent_relation in test_case.expected_absent_relations:
        assert not table_exists(db_path=db_path, table_name=absent_relation)


@pytest.mark.parametrize(
    "test_case",
    [
        DbtScenarioCliTestCase(
            description="dbt scenario test targets a dbt model with a source mock",
            command=("--no-color", "dbt", "scenario", "test", "dbt_stg_scenario_orders"),
            expected_stdout_fragments=(
                "Scenario (1 selected)",
                "dbt_stg_scenario_orders",
                "expect    expected stg_scenario_orders",
                "expect    assertion no_zero_orders",
                "PASS=1  FAIL=0  TOTAL=1",
            ),
        )
    ],
    ids=["dbt scenario test targets a dbt model with a source mock"],
)
def test_given_dbt_scenario_target_when_running_dbt_scenario_then_validates_dbt_model(
    test_case: DbtScenarioCliTestCase,
    tmp_path: Path,
) -> None:
    skip_unless_dbt_is_runnable()
    project_dir: Path = prepare_dbt_interop_project(tmp_path=tmp_path)
    write_dbt_scenario_targeting_dbt_model(project_dir=project_dir)

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.command,
        project_dir=project_dir,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    expected_stdout_fragment: str
    for expected_stdout_fragment in test_case.expected_stdout_fragments:
        assert expected_stdout_fragment in result.stdout


@pytest.mark.parametrize(
    "test_case",
    [
        DbtScenarioCliTestCase(
            description="dbt scenario test resolves a chained dbt model graph",
            command=("--no-color", "dbt", "scenario", "test", "dbt_fact_scenario_chain"),
            expected_stdout_fragments=(
                "Scenario (1 selected)",
                "dbt_fact_scenario_chain",
                "expect    expected fact_scenario_chain",
                "PASS=1  FAIL=0  TOTAL=1",
            ),
        )
    ],
    ids=["dbt scenario test resolves a chained dbt model graph"],
)
def test_given_chained_dbt_scenario_when_running_dbt_scenario_then_resolves_chain(
    test_case: DbtScenarioCliTestCase,
    tmp_path: Path,
) -> None:
    skip_unless_dbt_is_runnable()
    project_dir: Path = prepare_dbt_interop_project(tmp_path=tmp_path)
    write_chained_dbt_scenario_targeting_dbt_model(project_dir=project_dir)

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.command,
        project_dir=project_dir,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    expected_stdout_fragment: str
    for expected_stdout_fragment in test_case.expected_stdout_fragments:
        assert expected_stdout_fragment in result.stdout


@pytest.mark.parametrize(
    "test_case",
    [
        DbtScenarioCliTestCase(
            description="dbt scenario test reports a violated assertion as a failure",
            command=("--no-color", "dbt", "scenario", "test", "dbt_fail_assert"),
            expected_stdout_fragments=(
                "dbt_fail_assert",
                "expect    assertion no_zero_orders",
                "FAIL",
                "PASS=0  FAIL=1  TOTAL=1",
            ),
            expected_returncode=1,
        )
    ],
    ids=["dbt scenario test reports a violated assertion as a failure"],
)
def test_given_failing_assertion_when_running_dbt_scenario_then_fails(
    test_case: DbtScenarioCliTestCase,
    tmp_path: Path,
) -> None:
    skip_unless_dbt_is_runnable()
    project_dir: Path = prepare_dbt_interop_project(tmp_path=tmp_path)
    write_failing_assertion_dbt_scenario(project_dir=project_dir)

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.command,
        project_dir=project_dir,
    )

    assert result.returncode == test_case.expected_returncode, result.stdout + result.stderr
    expected_stdout_fragment: str
    for expected_stdout_fragment in test_case.expected_stdout_fragments:
        assert expected_stdout_fragment in result.stdout


@pytest.mark.parametrize(
    "test_case",
    [
        DbtScenarioCliTestCase(
            description="dbt scenario test reports a mismatched expected output as a failure",
            command=("--no-color", "dbt", "scenario", "test", "dbt_fail_expected"),
            expected_stdout_fragments=(
                "dbt_fail_expected",
                "expect    expected stg_scenario_fail_expected",
                "mismatched",
                "PASS=0  FAIL=1  TOTAL=1",
            ),
            expected_returncode=1,
        )
    ],
    ids=["dbt scenario test reports a mismatched expected output as a failure"],
)
def test_given_failing_expected_when_running_dbt_scenario_then_fails(
    test_case: DbtScenarioCliTestCase,
    tmp_path: Path,
) -> None:
    skip_unless_dbt_is_runnable()
    project_dir: Path = prepare_dbt_interop_project(tmp_path=tmp_path)
    write_failing_expected_dbt_scenario(project_dir=project_dir)

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.command,
        project_dir=project_dir,
    )

    assert result.returncode == test_case.expected_returncode, result.stdout + result.stderr
    expected_stdout_fragment: str
    for expected_stdout_fragment in test_case.expected_stdout_fragments:
        assert expected_stdout_fragment in result.stdout


@pytest.mark.parametrize(
    "test_case",
    [
        DbtScenarioCliTestCase(
            description="dbt scenario test targets a dbt model with a seed mock",
            command=("--no-color", "dbt", "scenario", "test", "dbt_dim_scenario_countries"),
            expected_stdout_fragments=(
                "Scenario (1 selected)",
                "dbt_dim_scenario_countries",
                "expect    expected dim_scenario_countries",
                "PASS=1  FAIL=0  TOTAL=1",
            ),
        )
    ],
    ids=["dbt scenario test targets a dbt model with a seed mock"],
)
def test_given_seed_dbt_scenario_when_running_dbt_scenario_then_validates_dbt_model(
    test_case: DbtScenarioCliTestCase,
    tmp_path: Path,
) -> None:
    skip_unless_dbt_is_runnable()
    project_dir: Path = prepare_dbt_interop_project(tmp_path=tmp_path)
    write_seed_dbt_scenario_targeting_dbt_model(project_dir=project_dir)

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.command,
        project_dir=project_dir,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    expected_stdout_fragment: str
    for expected_stdout_fragment in test_case.expected_stdout_fragments:
        assert expected_stdout_fragment in result.stdout


@pytest.mark.parametrize(
    "test_case",
    [
        DbtScenarioCliTestCase(
            description="dbt scenario test mocks an upstream dbt model as a ref boundary",
            command=("--no-color", "dbt", "scenario", "test", "dbt_fact_scenario_boundary"),
            expected_stdout_fragments=(
                "Scenario (1 selected)",
                "dbt_fact_scenario_boundary",
                "expect    expected fact_scenario_boundary",
                "PASS=1  FAIL=0  TOTAL=1",
            ),
        )
    ],
    ids=["dbt scenario test mocks an upstream dbt model as a ref boundary"],
)
def test_given_ref_boundary_dbt_scenario_when_running_dbt_scenario_then_uses_boundary(
    test_case: DbtScenarioCliTestCase,
    tmp_path: Path,
) -> None:
    skip_unless_dbt_is_runnable()
    project_dir: Path = prepare_dbt_interop_project(tmp_path=tmp_path)
    write_ref_boundary_dbt_scenario(project_dir=project_dir)

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.command,
        project_dir=project_dir,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    expected_stdout_fragment: str
    for expected_stdout_fragment in test_case.expected_stdout_fragments:
        assert expected_stdout_fragment in result.stdout


@pytest.mark.parametrize(
    "test_case",
    [
        DbtScenarioCliTestCase(
            description="dbt scenario test mocks a snapshot boundary",
            command=("--no-color", "dbt", "scenario", "test", "dbt_fact_orders_snapshot_scenario"),
            expected_stdout_fragments=(
                "Scenario (1 selected)",
                "dbt_fact_orders_snapshot_scenario",
                "expect    expected fact_orders_snapshot",
                "PASS=1  FAIL=0  TOTAL=1",
            ),
        )
    ],
    ids=["dbt scenario test mocks a snapshot boundary"],
)
def test_given_snapshot_boundary_dbt_scenario_when_running_dbt_scenario_then_uses_boundary(
    test_case: DbtScenarioCliTestCase,
    tmp_path: Path,
) -> None:
    skip_unless_dbt_is_runnable()
    project_dir: Path = prepare_dbt_interop_project(tmp_path=tmp_path)
    write_snapshot_boundary_dbt_scenario(project_dir=project_dir)

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.command,
        project_dir=project_dir,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    expected_stdout_fragment: str
    for expected_stdout_fragment in test_case.expected_stdout_fragments:
        assert expected_stdout_fragment in result.stdout


@pytest.mark.parametrize(
    "test_case",
    [
        DbtScenarioCliTestCase(
            description="dbt scenario test uses a package-qualified dbt source fixture",
            command=("--no-color", "dbt", "scenario", "test", "dbt_stg_scenario_qualified"),
            expected_stdout_fragments=(
                "Scenario (1 selected)",
                "dbt_stg_scenario_qualified",
                "expect    expected stg_scenario_qualified",
                "PASS=1  FAIL=0  TOTAL=1",
            ),
        )
    ],
    ids=["dbt scenario test uses a package-qualified dbt source fixture"],
)
def test_given_qualified_source_dbt_scenario_when_running_dbt_scenario_then_validates_dbt_model(
    test_case: DbtScenarioCliTestCase,
    tmp_path: Path,
) -> None:
    skip_unless_dbt_is_runnable()
    project_dir: Path = prepare_dbt_interop_project(tmp_path=tmp_path)
    write_qualified_source_dbt_scenario(project_dir=project_dir)
    deps_result: subprocess.CompletedProcess[str] = install_dbt_interop_packages(
        project_dir=project_dir
    )
    assert deps_result.returncode == 0, deps_result.stderr or deps_result.stdout

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.command,
        project_dir=project_dir,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    expected_stdout_fragment: str
    for expected_stdout_fragment in test_case.expected_stdout_fragments:
        assert expected_stdout_fragment in result.stdout


@pytest.mark.parametrize(
    "test_case",
    [
        DbtScenarioCliTestCase(
            description="dbt scenario test json output reports a passing scenario",
            command=("--no-color", "dbt", "scenario", "test", "dbt_stg_scenario_orders", "--json"),
            expected_stdout_fragments=('"status": "success"', '"name": "dbt_stg_scenario_orders"'),
        )
    ],
    ids=["dbt scenario test json output reports a passing scenario"],
)
def test_given_json_flag_when_running_dbt_scenario_then_emits_json(
    test_case: DbtScenarioCliTestCase,
    tmp_path: Path,
) -> None:
    skip_unless_dbt_is_runnable()
    project_dir: Path = prepare_dbt_interop_project(tmp_path=tmp_path)
    write_dbt_scenario_targeting_dbt_model(project_dir=project_dir)

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.command,
        project_dir=project_dir,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    expected_stdout_fragment: str
    for expected_stdout_fragment in test_case.expected_stdout_fragments:
        assert expected_stdout_fragment in result.stdout


@pytest.mark.parametrize(
    "test_case",
    [
        DbtScenarioCliTestCase(
            description="dbt scenario test retain keeps scenario-owned relations",
            command=(
                "--no-color",
                "dbt",
                "scenario",
                "test",
                "dbt_stg_scenario_orders",
                "--retain",
            ),
            expected_stdout_fragments=(
                "dbt_stg_scenario_orders",
                "Retained relations",
                "PASS=1  FAIL=0  TOTAL=1",
            ),
        )
    ],
    ids=["dbt scenario test retain keeps scenario-owned relations"],
)
def test_given_retain_flag_when_running_dbt_scenario_then_keeps_relations(
    test_case: DbtScenarioCliTestCase,
    tmp_path: Path,
) -> None:
    skip_unless_dbt_is_runnable()
    project_dir: Path = prepare_dbt_interop_project(tmp_path=tmp_path)
    write_dbt_scenario_targeting_dbt_model(project_dir=project_dir)

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.command,
        project_dir=project_dir,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    expected_stdout_fragment: str
    for expected_stdout_fragment in test_case.expected_stdout_fragments:
        assert expected_stdout_fragment in result.stdout


@pytest.mark.parametrize(
    "test_case",
    [
        DbtScenarioCliTestCase(
            description="dbt scenario fixture reads a real dbt source to build fixture data",
            command=("--no-color", "dbt", "scenario", "test", "dbt_real_source_fixture"),
            expected_stdout_fragments=(
                "Scenario (1 selected)",
                "dbt_real_source_fixture",
                "expect    expected stg_real_source_orders",
                "PASS=1  FAIL=0  TOTAL=1",
            ),
        )
    ],
    ids=["dbt scenario fixture reads a real dbt source to build fixture data"],
)
def test_given_real_source_fixture_when_running_dbt_scenario_then_reads_live_source(
    test_case: DbtScenarioCliTestCase,
    tmp_path: Path,
) -> None:
    skip_unless_dbt_is_runnable()
    project_dir: Path = prepare_dbt_interop_project(tmp_path=tmp_path)
    write_real_source_fixture_dbt_scenario(project_dir=project_dir)
    seed_real_dbt_source_orders(project_dir=project_dir)

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.command,
        project_dir=project_dir,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    expected_stdout_fragment: str
    for expected_stdout_fragment in test_case.expected_stdout_fragments:
        assert expected_stdout_fragment in result.stdout


@pytest.mark.parametrize(
    "test_case",
    [
        DbtScenarioCliTestCase(
            description="scenario over a SQLBuild model whose chain crosses a dbt ref boundary",
            command=("--no-color", "scenario", "test", "mart_orders_spanning"),
            expected_stdout_fragments=(
                "Scenario (1 selected)",
                "mart_orders_spanning",
                "expect    expected mart_orders",
                "expect    assertion mart_orders_nonzero",
                "PASS=1  FAIL=0  TOTAL=1",
            ),
            expected_absent_relations=("fact_orders",),
        )
    ],
    ids=["scenario over a SQLBuild model whose chain crosses a dbt ref boundary"],
)
def test_given_spanning_sqlbuild_dbt_graph_when_running_scenario_then_resolves_chain(
    test_case: DbtScenarioCliTestCase,
    tmp_path: Path,
) -> None:
    skip_unless_dbt_is_runnable()
    project_dir: Path = prepare_dbt_interop_project(tmp_path=tmp_path)
    setup_result: subprocess.CompletedProcess[str] = compile_dbt_interop_manifest(
        project_dir=project_dir
    )
    assert setup_result.returncode == 0, setup_result.stdout + setup_result.stderr
    write_spanning_sqlbuild_dbt_ref_scenario(project_dir=project_dir)

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.command,
        project_dir=project_dir,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    expected_stdout_fragment: str
    for expected_stdout_fragment in test_case.expected_stdout_fragments:
        assert expected_stdout_fragment in result.stdout
    db_path: Path = project_dir / "dbt_interop.duckdb"
    absent_relation: str
    for absent_relation in test_case.expected_absent_relations:
        assert not table_exists(db_path=db_path, table_name=absent_relation)


@pytest.mark.parametrize(
    "test_case",
    [
        DbtScenarioCliTestCase(
            description="dbt scenario test selects a single scenario via --select flag",
            command=(
                "--no-color",
                "dbt",
                "scenario",
                "test",
                "--select",
                "dbt_stg_scenario_orders",
            ),
            expected_stdout_fragments=(
                "Scenario (1 selected)",
                "dbt_stg_scenario_orders",
                "PASS=1  FAIL=0  TOTAL=1",
            ),
            expected_absent_stdout_fragments=("mart_orders_spanning",),
        )
    ],
    ids=["dbt scenario test selects a single scenario via --select flag"],
)
def test_given_select_flag_when_running_dbt_scenario_then_selects_named_scenario(
    test_case: DbtScenarioCliTestCase,
    tmp_path: Path,
) -> None:
    skip_unless_dbt_is_runnable()
    project_dir: Path = prepare_dbt_interop_project(tmp_path=tmp_path)
    write_dbt_scenario_targeting_dbt_model(project_dir=project_dir)
    write_spanning_sqlbuild_dbt_ref_scenario(project_dir=project_dir)

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.command,
        project_dir=project_dir,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    expected_stdout_fragment: str
    for expected_stdout_fragment in test_case.expected_stdout_fragments:
        assert expected_stdout_fragment in result.stdout
    absent_stdout_fragment: str
    for absent_stdout_fragment in test_case.expected_absent_stdout_fragments:
        assert absent_stdout_fragment not in result.stdout


@pytest.mark.parametrize(
    "test_case",
    [
        DbtScenarioCliTestCase(
            description="dbt scenario test excludes a scenario via --exclude flag",
            command=(
                "--no-color",
                "dbt",
                "scenario",
                "test",
                "--exclude",
                "mart_orders_spanning",
            ),
            expected_stdout_fragments=(
                "dbt_stg_scenario_orders",
                "PASS=2  FAIL=0  TOTAL=2",
            ),
            expected_absent_stdout_fragments=("mart_orders_spanning",),
        )
    ],
    ids=["dbt scenario test excludes a scenario via --exclude flag"],
)
def test_given_exclude_flag_when_running_dbt_scenario_then_drops_excluded_scenario(
    test_case: DbtScenarioCliTestCase,
    tmp_path: Path,
) -> None:
    skip_unless_dbt_is_runnable()
    project_dir: Path = prepare_dbt_interop_project(tmp_path=tmp_path)
    write_dbt_scenario_targeting_dbt_model(project_dir=project_dir)
    write_spanning_sqlbuild_dbt_ref_scenario(project_dir=project_dir)

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.command,
        project_dir=project_dir,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    expected_stdout_fragment: str
    for expected_stdout_fragment in test_case.expected_stdout_fragments:
        assert expected_stdout_fragment in result.stdout
    absent_stdout_fragment: str
    for absent_stdout_fragment in test_case.expected_absent_stdout_fragments:
        assert absent_stdout_fragment not in result.stdout


@pytest.mark.parametrize(
    "test_case",
    [
        DbtScenarioCliTestCase(
            description="dbt scenario test writes results to --json-output path",
            command=("--no-color", "dbt", "scenario", "test", "dbt_stg_scenario_orders"),
            expected_stdout_fragments=(),
            expected_json_command="scenario test",
        )
    ],
    ids=["dbt scenario test writes results to --json-output path"],
)
def test_given_json_output_path_when_running_dbt_scenario_then_writes_results_file(
    test_case: DbtScenarioCliTestCase,
    tmp_path: Path,
) -> None:
    skip_unless_dbt_is_runnable()
    project_dir: Path = prepare_dbt_interop_project(tmp_path=tmp_path)
    write_dbt_scenario_targeting_dbt_model(project_dir=project_dir)
    json_path: Path = project_dir / "scenario_results.json"

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=(*test_case.command, "--json-output", str(json_path)),
        project_dir=project_dir,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert json_path.exists()
    payload: object = json.loads(json_path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    assert payload["command"] == test_case.expected_json_command
    assert payload["scenarios"]
