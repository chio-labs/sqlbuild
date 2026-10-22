import json
import subprocess
from pathlib import Path

import pytest

from tests.integration.src.sqlbuild.cli.recall._test_types import (
    DocumentedQueryTestCase,
    FailureCauseTestCase,
    GitRevisionTestCase,
)
from tests.integration.src.sqlbuild.cli.recall.helpers import (
    DEPLOYED_REVISION,
    checkout_project,
    deployed_project,
    documented_commands,
    recall_rows,
    run,
    selected_columns,
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

ORCHESTRATED_CONTEXT: str = (
    '{"integration": {"name": "dagster", "job_name": "daily_models", "run_id": "run-7"}}'
)
WARNING_AUDITS: str = '\n[settings]\ndefault_audit_severity = "warn"\n'
CUSTOMERS_MODEL: str = (
    'MODEL (\n  description "One row per customer",\n  materialized table,\n'
    "  columns (email (audits [not_null])),\n);\n\n"
    "SELECT 1 AS customer_id, CAST(NULL AS VARCHAR) AS email\n"
)


@pytest.mark.parametrize(
    "test_case",
    [
        DocumentedQueryTestCase(
            description="an orchestrated job's runs are found by their external context",
            question=0,
            columns=("status",),
            expected_rows=[["completed"]],
        ),
        DocumentedQueryTestCase(
            description="the slowest models of a run are its model builds by resource",
            question=1,
            columns=("resource_name", "resource_kind"),
            expected_rows=[["customers", "table"], ["orders", "table"]],
        ),
        DocumentedQueryTestCase(
            description="audits that did not pass are listed",
            question=2,
            columns=("audit_name", "outcome", "violation_count"),
            expected_rows=[["not_null", "warn", 1]],
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_an_orchestrated_build_when_running_the_documented_queries_then_they_answer(
    test_case: DocumentedQueryTestCase, tmp_path: Path
) -> None:
    project_dir: Path = write_project(tmp_path / "orders_shop", extra_toml=WARNING_AUDITS)
    _ = (project_dir / "models" / "customers.sql").write_text(CUSTOMERS_MODEL, encoding="utf-8")
    built: subprocess.CompletedProcess[bytes] = run(
        project_dir, "build", SQLBUILD_INVOCATION_CONTEXT_JSON=ORCHESTRATED_CONTEXT
    )
    invocation_id: str = str(
        recall_rows(project_dir, "SELECT invocation_id FROM invocations")[0][0]
    )
    commands: list[list[str]] = documented_commands(invocation_id=invocation_id)

    answered: subprocess.CompletedProcess[bytes] = run(
        project_dir, *commands[test_case.question], "--json"
    )
    printed: subprocess.CompletedProcess[bytes] = run(project_dir, *commands[-1])

    assert built.returncode == 0, built.stderr
    assert len(commands) == 4
    assert answered.returncode == 0, answered.stderr
    assert (
        selected_columns(result=json.loads(answered.stdout), columns=test_case.columns)
        == test_case.expected_rows
    )
    assert printed.returncode == 0, printed.stderr
    assert len(printed.stdout.splitlines()) == 50
    assert printed.stdout.endswith(built.stdout.splitlines(keepends=True)[-1])


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
