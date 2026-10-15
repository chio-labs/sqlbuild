import subprocess
import sys
from pathlib import Path
from textwrap import dedent

import pytest

from tests.unit.src.sqlbuild.compiler.planner.classes._test_types import PlanningExitTestCase

_SLOW_TEST_PLANNING: str = dedent(
    """
    import sys
    import time
    import types

    import sqlbuild._native as native


    class SlowFinalizer:
        def __del__(self):
            print("finalizing", sys.is_finalizing(), file=sys.stderr, flush=True)
            time.sleep(2.0)


    holder = types.ModuleType("holder")
    holder.finalizer = SlowFinalizer()
    sys.modules["holder"] = holder
    plan_tests = native.plan_selected_sql_tests


    def slow_plan_selected_sql_tests(**arguments):
        time.sleep(1.0)
        return plan_tests(**arguments)


    native.plan_selected_sql_tests = slow_plan_selected_sql_tests
    """
)
_FAILED_BUILD: str = dedent(
    """
    from sqlbuild.cli.entry.main.entry import main
    from sqlbuild.compiler.planner.exceptions import PlannerInputError


    def failing_reconciliation(**arguments):
        raise PlannerInputError("forced planning failure")


    native.reconcile_execution_changes = failing_reconciliation
    sys.exit(main(["--project-dir", sys.argv[1], "--no-color", "build"]))
    """
)
_UNJOINED_PLANNING: str = dedent(
    """
    from sqlbuild._native import SqlTestSelection

    native.start_sql_test_planning(
        project=None,
        adapter=None,
        selected_keys=frozenset(),
        sql_test_selection=SqlTestSelection(),
        enabled=True,
    )
    print("planning started", file=sys.stderr, flush=True)
    """
)


@pytest.mark.parametrize(
    "test_case",
    (
        PlanningExitTestCase(
            "plan fails while SQL tests are still planning",
            _SLOW_TEST_PLANNING + _FAILED_BUILD,
            1,
            "error[S000]: forced planning failure",
        ),
        PlanningExitTestCase(
            "SQL test planning never joined",
            _SLOW_TEST_PLANNING + _UNJOINED_PLANNING,
            0,
            "planning started",
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_sql_test_planning_running_when_interpreter_finalizes_then_process_exits_cleanly(
    test_case: PlanningExitTestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = tmp_path / "orders_project"
    (project_dir / "models").mkdir(parents=True)
    (project_dir / "sqlbuild_project.toml").write_text(
        'name = "orders_project"\nadapter = "duckdb"\n\n'
        '[connection]\ndatabase = "orders_project.duckdb"\n',
        encoding="utf-8",
    )
    (project_dir / "models" / "orders.sql").write_text(
        "MODEL (description 'Test model orders.', materialized table);\n\nSELECT 1 AS order_id\n",
        encoding="utf-8",
    )
    script: Path = tmp_path / "planning_exit.py"
    script.write_text(test_case.script, encoding="utf-8")

    result: subprocess.CompletedProcess[str] = subprocess.run(
        [sys.executable, str(script), str(project_dir)],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )

    assert result.returncode == test_case.expected_returncode, result.stdout + result.stderr
    assert test_case.expected_output in result.stdout + result.stderr
    assert "finalizing True" in result.stderr
