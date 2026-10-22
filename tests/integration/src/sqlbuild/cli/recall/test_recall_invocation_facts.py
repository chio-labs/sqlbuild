import subprocess
from pathlib import Path

import pytest

from tests.integration.src.sqlbuild.cli.recall._test_types import (
    FailureCauseTestCase,
    GitRevisionTestCase,
)
from tests.integration.src.sqlbuild.cli.recall.helpers import (
    DEPLOYED_REVISION,
    checkout_project,
    deployed_project,
    recall_rows,
    run,
    worktree_project,
    write_project,
)

BROKEN_TARGET: str = (
    "\n[connections.broken]\n"
    'database = "missing_directory/warehouse.duckdb"\n\n'
    "[targets.broken]\n"
    'connection = "broken"\n'
    'schema = "dev"\n'
)


@pytest.mark.parametrize(
    "test_case",
    [
        FailureCauseTestCase(
            description="a debug connection failure reported by exit code",
            args=("debug", "--target", "broken"),
            expected_failure=["debug", "failed", 1, "ConnectionError", "C980"],
            expected_message_prefix="connection test: ",
        ),
        FailureCauseTestCase(
            description="a raised coded error",
            args=("build", "--select", "no_such_model"),
            expected_failure=["build", "failed", None, "PlannerInputError", "S007"],
            expected_message_prefix="unknown selector name 'no_such_model'",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_a_failed_command_when_recorded_then_its_cause_is_structured(
    test_case: FailureCauseTestCase, tmp_path: Path
) -> None:
    project_dir: Path = write_project(tmp_path / "orders_shop", extra_toml=BROKEN_TARGET)

    failed: subprocess.CompletedProcess[bytes] = run(project_dir, *test_case.args)
    recorded: list[list[object]] = recall_rows(
        project_dir,
        "SELECT command, status, exit_code, error_type, error_code, error_message FROM invocations",
    )

    assert failed.returncode != 0
    assert [row[:5] for row in recorded] == [test_case.expected_failure]
    assert str(recorded[0][5]).startswith(test_case.expected_message_prefix)


@pytest.mark.parametrize(
    "test_case",
    [
        GitRevisionTestCase(
            description="the deployment's override wins",
            prepare=deployed_project,
            environment={"SQLBUILD_GIT_REVISION": DEPLOYED_REVISION, "SQLBUILD_GIT_DIRTY": "true"},
            expected_dirty=1,
        ),
        GitRevisionTestCase(
            description="a git worktree reads HEAD through its .git file",
            prepare=worktree_project,
            environment={},
            expected_dirty=None,
        ),
        GitRevisionTestCase(
            description="a plain checkout reads HEAD from .git",
            prepare=checkout_project,
            environment={},
            expected_dirty=None,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_a_deployment_or_checkout_when_recorded_then_the_git_revision_is_known(
    test_case: GitRevisionTestCase, tmp_path: Path
) -> None:
    project_dir, expected_revision = test_case.prepare(tmp_path)

    built: subprocess.CompletedProcess[bytes] = run(project_dir, "build", **test_case.environment)

    assert built.returncode == 0, built.stderr.decode(errors="replace")
    assert recall_rows(project_dir, "SELECT git_revision, git_dirty FROM invocations") == [
        [expected_revision, test_case.expected_dirty]
    ]
