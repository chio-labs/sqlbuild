from __future__ import annotations

from collections.abc import Callable
from io import StringIO
from typing import cast

import pytest

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.cli.commands._helpers.dbt import sqlbuild_work as work_module
from sqlbuild.cli.commands._helpers.dbt.models import DbtSqlbuildWorkContext
from sqlbuild.cli.commands._helpers.dbt.sqlbuild_work import execute_sqlbuild_test_work
from sqlbuild.compiler.planner.models import PlanOutput, SqlTestPlanEntry
from sqlbuild.executor.testing.models import SqlTestExecutionResult
from sqlbuild.executor.testing.types import SqlTestOutcome
from sqlbuild.integrations.dbt.types import DbtInteropSqlbuildTestAction
from sqlbuild.presentation.classes.cli_style import CliStyle
from sqlbuild.runtime.contracts.types import ConnectionElapsedCallback
from tests.unit.src.sqlbuild.cli.commands._helpers._test_types import (
    DbtSqlbuildWorkOutputTestCase,
)
from tests.unit.src.sqlbuild.cli.commands._helpers.helpers import chained_sql_test_entry


@pytest.mark.parametrize(
    "test_case",
    [
        DbtSqlbuildWorkOutputTestCase(
            description="skips empty test and audit phases",
            expected_fragments=(),
            unexpected_fragments=(
                "SQLBuild execution  sqb test",
                "SQLBuild execution  sqb audit",
                "Test (0 selected",
                "Audit (0 selected",
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_empty_sqlbuild_test_work_when_executing_then_skips_empty_phases(
    test_case: DbtSqlbuildWorkOutputTestCase,
) -> None:
    output_stream: StringIO = StringIO()

    exit_code: int = execute_sqlbuild_test_work(
        context=DbtSqlbuildWorkContext(
            plan_output=PlanOutput(),
            connection_config={},
            adapter=cast(BaseAdapter, object()),
            adapter_name="duckdb",
            output_stream=output_stream,
            use_color=False,
        ),
        actions=(DbtInteropSqlbuildTestAction.TEST, DbtInteropSqlbuildTestAction.AUDIT),
    )

    rendered: str = output_stream.getvalue()
    assert exit_code == 0
    for expected_fragment in test_case.expected_fragments:
        assert expected_fragment in rendered
    for unexpected_fragment in test_case.unexpected_fragments:
        assert unexpected_fragment not in rendered


@pytest.mark.parametrize(
    "test_case",
    [
        DbtSqlbuildWorkOutputTestCase(
            description="separates test preflight from first test row",
            expected_fragments=("Prepared test functions. (0.00s)\n\nfct_orders",),
            unexpected_fragments=(
                "Prepared test functions. (0.00s)\nfct_orders",
                "stg_orders",
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_sqlbuild_test_work_when_preflight_completes_then_separates_first_row(
    test_case: DbtSqlbuildWorkOutputTestCase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_stream: StringIO = StringIO()

    def fake_run_test_pipeline(**kwargs: object) -> tuple[SqlTestExecutionResult, ...]:
        on_connection_complete: ConnectionElapsedCallback = cast(
            ConnectionElapsedCallback, kwargs["on_connection_complete"]
        )
        on_progress: Callable[[str], None] = cast(Callable[[str], None], kwargs["on_progress"])
        on_test_start: Callable[[SqlTestPlanEntry], None] = cast(
            Callable[[SqlTestPlanEntry], None], kwargs["on_test_start"]
        )
        on_test_complete: Callable[[SqlTestExecutionResult], None] = cast(
            Callable[[SqlTestExecutionResult], None], kwargs["on_test_complete"]
        )
        on_connection_complete(1, elapsed_seconds=0.0)
        on_progress("Preparing test functions...")
        on_progress("Prepared test functions. (0.00s)")
        entry: SqlTestPlanEntry = chained_sql_test_entry()
        on_test_start(entry)
        result: SqlTestExecutionResult = SqlTestExecutionResult(
            test_name="test_orders",
            outcome=SqlTestOutcome.PASS,
            step_results=(),
        )
        on_test_complete(result)
        return (result,)

    monkeypatch.setattr(work_module, "run_test_pipeline", fake_run_test_pipeline)

    execute_sqlbuild_test_work(
        context=DbtSqlbuildWorkContext(
            plan_output=PlanOutput(test_entries=(chained_sql_test_entry(),)),
            connection_config={},
            adapter=cast(BaseAdapter, object()),
            adapter_name="duckdb",
            output_stream=output_stream,
            use_color=False,
        ),
        actions=(DbtInteropSqlbuildTestAction.TEST,),
    )

    rendered: str = output_stream.getvalue()
    for expected_fragment in test_case.expected_fragments:
        assert expected_fragment in rendered
    for unexpected_fragment in test_case.unexpected_fragments:
        assert unexpected_fragment not in rendered


@pytest.mark.parametrize(
    "test_case",
    [
        DbtSqlbuildWorkOutputTestCase(
            description="styles the test header with success_strong color",
            expected_fragments=(CliStyle(use_color=True).success_strong("Test (1 selected)"),),
            unexpected_fragments=("\nTest (1 selected)\n",),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_sqlbuild_test_work_when_rendering_header_then_uses_success_strong_color(
    test_case: DbtSqlbuildWorkOutputTestCase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_stream: StringIO = StringIO()

    def fake_run_test_pipeline(**kwargs: object) -> tuple[SqlTestExecutionResult, ...]:
        on_test_complete: Callable[[SqlTestExecutionResult], None] = cast(
            Callable[[SqlTestExecutionResult], None], kwargs["on_test_complete"]
        )
        result: SqlTestExecutionResult = SqlTestExecutionResult(
            test_name="test_orders",
            outcome=SqlTestOutcome.PASS,
            step_results=(),
        )
        on_test_complete(result)
        return (result,)

    monkeypatch.setattr(work_module, "run_test_pipeline", fake_run_test_pipeline)

    execute_sqlbuild_test_work(
        context=DbtSqlbuildWorkContext(
            plan_output=PlanOutput(test_entries=(chained_sql_test_entry(),)),
            connection_config={},
            adapter=cast(BaseAdapter, object()),
            adapter_name="duckdb",
            output_stream=output_stream,
            use_color=True,
        ),
        actions=(DbtInteropSqlbuildTestAction.TEST,),
    )

    rendered: str = output_stream.getvalue()
    for expected_fragment in test_case.expected_fragments:
        assert expected_fragment in rendered
    for unexpected_fragment in test_case.unexpected_fragments:
        assert unexpected_fragment not in rendered
