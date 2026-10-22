"""`sqb test --since` and `sqb scenario test --since` select what a git change can affect."""

import json
from pathlib import Path
from subprocess import CompletedProcess

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.test._test_types import (
    SinceJsonOutputE2ETestCase,
    SinceSelectionE2ETestCase,
    SinceShallowCloneE2ETestCase,
    SinceSharedBaseE2ETestCase,
)
from tests.e2e.src.sqlbuild.cli.commands.main.test.helpers import (
    build_since_project_files,
    delete_project_files,
    prepare_since_repository,
    run_git,
    write_project_files,
)
from tests.e2e.src.sqlbuild.cli.commands.shared.helpers import run_sqb

_FILES: dict[str, str] = build_since_project_files()
_STAGING: str = "models/stg_orders.sql"
_MACRO: str = "models/_macros/money.py"
_EDITED_STAGING: str = _FILES[_STAGING].replace(
    "SELECT order_id, status", "SELECT order_id, LOWER(status) AS status"
)
_EDITED_MACRO: str = _FILES[_MACRO].replace("/ 100", "/ 100.0")
_REFORMATTED_STAGING: str = (
    "MODEL (description 'Cleaned and documented orders.');\n\n"
    "-- one row per order\nselect\n  order_id,\n  status,\n  amount_cents\n"
    'from __source("raw_orders")\n'
)
_ARCHIVE: str = "models/order_archive.sql"
_ARCHIVE_SQL: str = (
    "MODEL (description 'Archived orders.');\n\nSELECT order_id FROM __ref(\"stg_orders\")\n"
)
_TEST_COMMAND: tuple[str, ...] = ("--no-color", "test", "--since", "main")
_BASE_REF_CONFIG: str = _FILES["sqlbuild_project.toml"] + '\n[git]\nbase_ref = "main"\n'


@pytest.mark.parametrize(
    "test_case",
    (
        SinceSelectionE2ETestCase(
            description="an uncommitted model edit selects only the test that really runs it",
            edits={_STAGING: _EDITED_STAGING},
            command=(*_TEST_COMMAND, "--explain"),
            expected_exit_code=0,
            expected_fragments=(
                "Comparing with main (merge base ",
                "Compiled base revision ",
                "Changed since main: 1 model changed",
                "Selected 1 of 3 tests",
                "test_stg_orders\n    executes stg_orders (model SQL changed)",
                "PASS=1  FAIL=0  TOTAL=1",
            ),
            unexpected_fragments=("test_order_totals", "test_open_orders"),
        ),
        SinceSelectionE2ETestCase(
            description="a committed macro edit selects the test whose model calls the macro",
            edits={_MACRO: _EDITED_MACRO},
            command=(*_TEST_COMMAND, "--explain"),
            expected_exit_code=0,
            expected_fragments=(
                "Changed since main: 1 macro changed",
                "test_order_totals\n    executes macro cents_to_dollars (changed)",
                "PASS=1  FAIL=0  TOTAL=1",
            ),
            unexpected_fragments=("test_stg_orders", "test_open_orders"),
            git_after_edits=("commit", "--quiet", "--all", "-m", "edit"),
        ),
        SinceSelectionE2ETestCase(
            description="formatting, comments and descriptions change nothing",
            edits={_STAGING: _REFORMATTED_STAGING},
            command=_TEST_COMMAND,
            expected_exit_code=0,
            expected_fragments=(
                "Changed since main: no definition changes",
                "No tests are affected by the changes since main",
                "PASS=0  FAIL=0  TOTAL=0",
            ),
        ),
        SinceSelectionE2ETestCase(
            description="an edited test file selects that test",
            edits={
                "tests/unit/test_open_orders.sql": _FILES["tests/unit/test_open_orders.sql"]
                + "-- covers open orders\n"
            },
            command=(*_TEST_COMMAND, "--inspect"),
            expected_exit_code=0,
            expected_fragments=(
                "Selected 1 of 3 tests",
                "test_open_orders\n",
                "  selected: test file changed",
                "Test plan inspection complete: 1 selected, 0 errors.",
            ),
            unexpected_fragments=("test_stg_orders\n", "test_order_totals\n"),
        ),
        SinceSelectionE2ETestCase(
            description="selectors intersect with the affected tests",
            edits={_STAGING: _EDITED_STAGING, _MACRO: _EDITED_MACRO},
            command=(*_TEST_COMMAND, "order_totals"),
            expected_exit_code=0,
            expected_fragments=("Selected 1 of 1 test\n", "PASS=1  FAIL=0  TOTAL=1"),
            unexpected_fragments=("test_stg_orders",),
        ),
        SinceSelectionE2ETestCase(
            description="exclude removes affected tests",
            edits={_STAGING: _EDITED_STAGING, _MACRO: _EDITED_MACRO},
            command=(*_TEST_COMMAND, "--exclude", "test:test_order_totals"),
            expected_exit_code=0,
            expected_fragments=("Selected 1 of 2 tests", "PASS=1  FAIL=0  TOTAL=1"),
            unexpected_fragments=("test_order_totals",),
        ),
        SinceSelectionE2ETestCase(
            description="a deleted model is listed and selects nothing",
            edits={},
            deletions=(_ARCHIVE,),
            command=_TEST_COMMAND,
            expected_exit_code=0,
            expected_fragments=(
                "Changed since main: deleted: model order_archive",
                "No tests are affected by the changes since main",
            ),
        ),
        SinceSelectionE2ETestCase(
            description="a pure rename through migrate_from selects nothing",
            edits={
                "models/order_history.sql": _ARCHIVE_SQL.replace(
                    "MODEL (", "MODEL (migrate_from order_archive, "
                ),
            },
            deletions=(_ARCHIVE,),
            command=_TEST_COMMAND,
            expected_exit_code=0,
            expected_fragments=(
                "Changed since main: 1 model renamed",
                "No tests are affected by the changes since main",
            ),
            unexpected_fragments=("deleted:",),
        ),
        SinceSelectionE2ETestCase(
            description="a missing ref fails instead of selecting nothing",
            edits={},
            command=("--no-color", "test", "--since", "origin/missing"),
            expected_exit_code=1,
            expected_fragments=(
                "error[C481]: Git ref 'origin/missing' does not name a commit in this repository",
                "git fetch origin <branch>",
            ),
        ),
        SinceSelectionE2ETestCase(
            description="@base without a configured base ref fails",
            edits={},
            command=("--no-color", "test", "--since", "@base"),
            expected_exit_code=1,
            expected_fragments=(
                "error[C485]: --since @base needs [git] base_ref in sqlbuild_project.toml",
            ),
        ),
        SinceSelectionE2ETestCase(
            description="--explain needs --since",
            edits={},
            command=("--no-color", "test", "--explain"),
            expected_exit_code=2,
            expected_fragments=("--explain requires --since",),
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_changes_since_ref_when_testing_then_runs_only_affected_tests(
    tmp_path: Path, test_case: SinceSelectionE2ETestCase
) -> None:
    project: Path = prepare_since_repository(
        tmp_path=tmp_path, extra_files={_ARCHIVE: _ARCHIVE_SQL}
    )
    write_project_files(project_dir=project, files=test_case.edits)
    delete_project_files(project_dir=project, relative_paths=test_case.deletions)
    run_git(repository=project, arguments=test_case.git_after_edits)

    result: CompletedProcess[str] = run_sqb(command=test_case.command, project_dir=project)

    output: str = result.stdout + result.stderr
    assert result.returncode == test_case.expected_exit_code, output
    for fragment in test_case.expected_fragments:
        assert fragment in output, output
    for fragment in test_case.unexpected_fragments:
        assert fragment not in output, output


@pytest.mark.parametrize(
    "test_case",
    (
        SinceSharedBaseE2ETestCase(
            description="a scenario run reuses the base compile of the test run",
            edits={_STAGING: _EDITED_STAGING, "sqlbuild_project.toml": _BASE_REF_CONFIG},
            test_command=("--no-color", "test", "--since", "@base"),
            scenario_command=("--no-color", "scenario", "test", "--since", "@base", "--explain"),
            expected_test_fragments=("Compiled base revision ", "Selected 1 of 3 tests"),
            expected_scenario_fragments=(
                "Using cached base revision ",
                "Changed since main: 1 model changed",
                "Selected 1 of 2 scenarios",
                "order_totals_end_to_end\n    executes stg_orders (model SQL changed)",
                "PASS=1  FAIL=0  TOTAL=1",
            ),
            unexpected_scenario_fragments=("open_orders_from_fixture",),
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_test_and_scenario_runs_when_comparing_then_both_share_one_base_compile(
    tmp_path: Path, test_case: SinceSharedBaseE2ETestCase
) -> None:
    project: Path = prepare_since_repository(tmp_path=tmp_path, extra_files={})
    write_project_files(project_dir=project, files=test_case.edits)

    tested: CompletedProcess[str] = run_sqb(command=test_case.test_command, project_dir=project)
    scenarios: CompletedProcess[str] = run_sqb(
        command=test_case.scenario_command, project_dir=project
    )

    tested_output: str = tested.stdout + tested.stderr
    scenario_output: str = scenarios.stdout + scenarios.stderr
    assert tested.returncode == 0, tested_output
    assert scenarios.returncode == 0, scenario_output
    for fragment in test_case.expected_test_fragments:
        assert fragment in tested_output, tested_output
    for fragment in test_case.expected_scenario_fragments:
        assert fragment in scenario_output, scenario_output
    for fragment in test_case.unexpected_scenario_fragments:
        assert fragment not in scenario_output, scenario_output


@pytest.mark.parametrize(
    "test_case",
    (
        SinceJsonOutputE2ETestCase(
            description="progress and the selection go to stderr",
            edits={_STAGING: _EDITED_STAGING},
            command=("--no-color", "test", "--since", "main", "--json"),
            expected_stderr_fragments=("Comparing with main", "Selected 1 of 3 tests"),
            expected_test_names=("test_stg_orders",),
            unexpected_stdout_fragments=("test_order_totals", "Comparing with"),
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_json_output_when_testing_since_ref_then_stdout_stays_machine_readable(
    tmp_path: Path, test_case: SinceJsonOutputE2ETestCase
) -> None:
    project: Path = prepare_since_repository(tmp_path=tmp_path, extra_files={})
    write_project_files(project_dir=project, files=test_case.edits)

    result: CompletedProcess[str] = run_sqb(command=test_case.command, project_dir=project)

    assert result.returncode == 0, result.stdout + result.stderr
    document: str = json.dumps(json.loads(result.stdout))
    for fragment in test_case.expected_stderr_fragments:
        assert fragment in result.stderr, result.stderr
    for name in test_case.expected_test_names:
        assert f'"{name}"' in document, document
    for fragment in test_case.unexpected_stdout_fragments:
        assert fragment not in result.stdout, result.stdout


@pytest.mark.parametrize(
    "test_case",
    (
        SinceShallowCloneE2ETestCase(
            description="a depth-one clone of both branches lacks the merge base",
            clone_arguments=("--depth", "1", "--branch", "feature", "--no-single-branch"),
            fetch_arguments=("fetch", "--quiet", "--depth", "1", "origin", "main"),
            command=("--no-color", "test", "--since", "origin/main"),
            expected_exit_code=1,
            expected_fragments=(
                "error[C482]: Cannot find the merge base of 'origin/main' and HEAD",
                "git fetch --unshallow",
            ),
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_shallow_clone_without_merge_base_when_testing_since_then_asks_for_depth(
    tmp_path: Path, test_case: SinceShallowCloneE2ETestCase
) -> None:
    origin: Path = prepare_since_repository(tmp_path=tmp_path, extra_files={})
    run_git(repository=origin, arguments=("commit", "--quiet", "--allow-empty", "-m", "next"))
    clone: Path = tmp_path / "clone"
    run_git(
        repository=tmp_path,
        arguments=("clone", "--quiet", *test_case.clone_arguments, origin.as_uri(), str(clone)),
    )
    run_git(repository=clone, arguments=test_case.fetch_arguments)

    result: CompletedProcess[str] = run_sqb(command=test_case.command, project_dir=clone)

    output: str = result.stdout + result.stderr
    assert result.returncode == test_case.expected_exit_code, output
    for fragment in test_case.expected_fragments:
        assert fragment in output, output
