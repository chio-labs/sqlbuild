"""Unit tests for build progress output helpers."""

from __future__ import annotations

import time
from io import StringIO

import pytest

from sqlbuild.cli.commands.main.shared.helpers.nested_progress import NestedCommandProgressCallbacks
from sqlbuild.cli.commands.main.shared.helpers.progress import (
    BuildProgressCallbacks,
    _aggregate_audit_results,
    _AuditDisplayEntry,
    _truncate_name,
    format_build_footer,
)
from sqlbuild.cli.commands.main.shared.models import NestedProgressChildRow
from sqlbuild.compiler.auditing.types import AuditOutcome, AuditRunScope
from sqlbuild.compiler.planner.models import PlanOutput
from sqlbuild.compiler.planner.types import MaterializationType
from sqlbuild.executor.build.models import (
    BuildExecutionResult,
    FunctionExecutionResult,
    SeedExecutionResult,
)
from sqlbuild.executor.build.types import BuildStatus
from sqlbuild.executor.run.models import ModelExecutionResult
from sqlbuild.executor.shared.types import ExecutionPhase, ExecutionStatus
from sqlbuild.executor.testing.models import SqlTestExecutionResult, StepResult
from sqlbuild.executor.testing.types import SqlTestOutcome
from tests.unit.src.sqlbuild.cli.commands.main.shared.helpers._test_types import (
    AuditAggregationTestCase,
    BuildFooterTestCase,
    BuildProgressActiveSpinnerTestCase,
    BuildProgressFailureOutputTestCase,
    BuildProgressModelOutputTestCase,
    BuildProgressSpinnerLifecycleTestCase,
    BuildProgressSqlTestRowsTestCase,
    NestedProgressChildRowsTestCase,
    TruncateNameTestCase,
)
from tests.unit.src.sqlbuild.cli.commands.main.shared.helpers.helpers import (
    build_audit_result,
    build_progress_snapshot_plan_output,
)

TRUNCATE_NAME_TEST_CASES: list[TruncateNameTestCase] = [
    TruncateNameTestCase(
        description="name shorter than width is returned unchanged",
        name="orders",
        width=20,
        expected_result="orders",
    ),
    TruncateNameTestCase(
        description="name exactly at width is returned unchanged",
        name="orders",
        width=6,
        expected_result="orders",
    ),
    TruncateNameTestCase(
        description="name longer than width is truncated with ellipsis",
        name="very_long_model_name_that_exceeds_limit",
        width=20,
        expected_result="very_long_model_n...",
    ),
    TruncateNameTestCase(
        description="name one char over width truncates correctly",
        name="abcdefgh",
        width=7,
        expected_result="abcd...",
    ),
]


@pytest.mark.parametrize(
    "test_case",
    TRUNCATE_NAME_TEST_CASES,
    ids=[case.description for case in TRUNCATE_NAME_TEST_CASES],
)
def test_given_name_and_width_when_truncating_then_returns_expected_result(
    test_case: TruncateNameTestCase,
) -> None:
    result: str = _truncate_name(test_case.name, test_case.width)

    assert result == test_case.expected_result


AUDIT_AGGREGATION_TEST_CASES: list[AuditAggregationTestCase] = [
    AuditAggregationTestCase(
        description="final-only audits produce one entry per audit with audit label",
        audit_results=(
            build_audit_result(name="not_null", outcome=AuditOutcome.PASS, column_name="id"),
            build_audit_result(name="unique", outcome=AuditOutcome.PASS, column_name="id"),
        ),
        expected_entry_count=2,
        expected_labels=("audit", "audit"),
        expected_outcomes=(AuditOutcome.PASS, AuditOutcome.PASS),
        expected_batch_totals=(1, 1),
        expected_batch_passes=(1, 1),
    ),
    AuditAggregationTestCase(
        description="delta_and_final audits produce separate delta and final entries",
        audit_results=(
            build_audit_result(
                name="not_null",
                outcome=AuditOutcome.PASS,
                column_name="id",
                run_scope_phase=AuditRunScope.DELTA_AND_FINAL,
            ),
            build_audit_result(
                name="not_null",
                outcome=AuditOutcome.PASS,
                column_name="id",
                run_scope_phase=AuditRunScope.FINAL,
            ),
        ),
        expected_entry_count=2,
        expected_labels=("audit (d)", "audit (f)"),
        expected_outcomes=(AuditOutcome.PASS, AuditOutcome.PASS),
        expected_batch_totals=(1, 1),
        expected_batch_passes=(1, 1),
    ),
    AuditAggregationTestCase(
        description="multiple delta batches aggregate into one entry with batch count",
        audit_results=(
            build_audit_result(
                name="not_null",
                outcome=AuditOutcome.PASS,
                column_name="id",
                run_scope_phase=AuditRunScope.DELTA_AND_FINAL,
            ),
            build_audit_result(
                name="not_null",
                outcome=AuditOutcome.PASS,
                column_name="id",
                run_scope_phase=AuditRunScope.DELTA_AND_FINAL,
            ),
            build_audit_result(
                name="not_null",
                outcome=AuditOutcome.PASS,
                column_name="id",
                run_scope_phase=AuditRunScope.DELTA_AND_FINAL,
            ),
            build_audit_result(
                name="not_null",
                outcome=AuditOutcome.PASS,
                column_name="id",
                run_scope_phase=AuditRunScope.FINAL,
            ),
        ),
        expected_entry_count=2,
        expected_labels=("audit (d)", "audit (f)"),
        expected_outcomes=(AuditOutcome.PASS, AuditOutcome.PASS),
        expected_batch_totals=(3, 1),
        expected_batch_passes=(3, 1),
    ),
    AuditAggregationTestCase(
        description="worst outcome across batches is reported when one batch fails",
        audit_results=(
            build_audit_result(
                name="not_null",
                outcome=AuditOutcome.PASS,
                column_name="id",
                run_scope_phase=AuditRunScope.DELTA_AND_FINAL,
            ),
            build_audit_result(
                name="not_null",
                outcome=AuditOutcome.ERROR,
                column_name="id",
                row_count=5,
                run_scope_phase=AuditRunScope.DELTA_AND_FINAL,
            ),
            build_audit_result(
                name="not_null",
                outcome=AuditOutcome.PASS,
                column_name="id",
                run_scope_phase=AuditRunScope.DELTA_AND_FINAL,
            ),
            build_audit_result(
                name="not_null",
                outcome=AuditOutcome.PASS,
                column_name="id",
                run_scope_phase=AuditRunScope.FINAL,
            ),
        ),
        expected_entry_count=2,
        expected_labels=("audit (d)", "audit (f)"),
        expected_outcomes=(AuditOutcome.ERROR, AuditOutcome.PASS),
        expected_batch_totals=(3, 1),
        expected_batch_passes=(2, 1),
    ),
    AuditAggregationTestCase(
        description="warn is worst outcome when no errors present",
        audit_results=(
            build_audit_result(
                name="row_check",
                outcome=AuditOutcome.PASS,
                run_scope_phase=AuditRunScope.DELTA_AND_FINAL,
            ),
            build_audit_result(
                name="row_check",
                outcome=AuditOutcome.WARN,
                row_count=2,
                run_scope_phase=AuditRunScope.DELTA_AND_FINAL,
            ),
            build_audit_result(
                name="row_check",
                outcome=AuditOutcome.PASS,
                run_scope_phase=AuditRunScope.FINAL,
            ),
        ),
        expected_entry_count=2,
        expected_labels=("audit (d)", "audit (f)"),
        expected_outcomes=(AuditOutcome.WARN, AuditOutcome.PASS),
        expected_batch_totals=(2, 1),
        expected_batch_passes=(1, 1),
    ),
]


BUILD_FOOTER_TEST_CASES: list[BuildFooterTestCase] = [
    BuildFooterTestCase(
        description="failed function result includes failure count and error",
        result=BuildExecutionResult(
            status=BuildStatus.FAILED,
            function_results=(
                FunctionExecutionResult(
                    function_name="is_completed_order",
                    status=ExecutionStatus.FAILED,
                    error_message="warehouse said no",
                ),
            ),
        ),
        expected_fragments=(
            "FAIL=1",
            "is_completed_order  (function)",
            "warehouse said no",
        ),
    ),
    BuildFooterTestCase(
        description="failed seed result includes failure count and error",
        result=BuildExecutionResult(
            status=BuildStatus.FAILED,
            seed_results=(
                SeedExecutionResult(
                    seed_name="waffle_types",
                    status=ExecutionStatus.FAILED,
                    error_message="failed to load seed CSV",
                ),
            ),
        ),
        expected_fragments=(
            "FAIL=1",
            "waffle_types  (seed)",
            "failed to load seed CSV",
        ),
    ),
    BuildFooterTestCase(
        description="function warning appears in summary and warnings section",
        result=BuildExecutionResult(
            status=BuildStatus.SUCCESS,
            function_results=(
                FunctionExecutionResult(
                    function_name="is_completed_order_py",
                    status=ExecutionStatus.SUCCESS,
                    warning_messages=("fingerprint write skipped",),
                ),
            ),
            success_count=1,
            warning_count=1,
        ),
        expected_fragments=(
            "Completed with warnings.",
            "PASS=1",
            "WARN=1",
            "Warnings:",
            "is_completed_order_py  (function)",
            "fingerprint write skipped",
        ),
    ),
    BuildFooterTestCase(
        description="footer failure error text truncates after four lines",
        result=BuildExecutionResult(
            status=BuildStatus.FAILED,
            function_results=(
                FunctionExecutionResult(
                    function_name="is_completed_order",
                    status=ExecutionStatus.FAILED,
                    error_message=(
                        "line one\nline two\nline three\nline four\nline five should not appear"
                    ),
                ),
            ),
        ),
        expected_fragments=(
            "Failures:",
            "error     line one",
            "line two",
            "line three",
            "line four...",
        ),
        unexpected_fragments=("line five should not appear",),
    ),
]

BUILD_PROGRESS_FAILURE_OUTPUT_TEST_CASES: list[BuildProgressFailureOutputTestCase] = [
    BuildProgressFailureOutputTestCase(
        description="failed seed writes error detail below result row",
        node_result=SeedExecutionResult(
            seed_name="waffle_types",
            status=ExecutionStatus.FAILED,
            duration_ms=30,
            error_message="failed to load seed CSV",
        ),
        expected_fragments=(
            "seed      waffle_types",
            "FAIL",
            "0.03s",
            "error     failed to load seed CSV",
        ),
        unexpected_fragments=("0.03s  failed to load seed CSV",),
    ),
    BuildProgressFailureOutputTestCase(
        description="failed function writes multiline error detail below result row",
        node_result=FunctionExecutionResult(
            function_name="is_completed_order",
            status=ExecutionStatus.FAILED,
            duration_ms=110,
            error_message=(
                "003001 (42501): SQL access control error:\n"
                "Insufficient privileges to operate on schema 'TEST'."
            ),
        ),
        expected_fragments=(
            "function  is_completed_order",
            "FAIL",
            "0.11s",
            "error     003001 (42501): SQL access control error:",
            "          Insufficient privileges to operate on schema 'TEST'.",
        ),
        unexpected_fragments=("0.11s  003001",),
    ),
    BuildProgressFailureOutputTestCase(
        description="failed model keeps phase on row and writes error below",
        node_result=ModelExecutionResult(
            model_name="fact_orders",
            status=ExecutionStatus.FAILED,
            failed_phase=ExecutionPhase.STAGING,
            duration_ms=420,
            error_message="relation raw_orders does not exist",
        ),
        expected_fragments=(
            "table     fact_orders",
            "FAIL",
            "0.42s  staging",
            "error     relation raw_orders does not exist",
        ),
        unexpected_fragments=("staging  relation raw_orders does not exist",),
    ),
    BuildProgressFailureOutputTestCase(
        description="live error detail truncates after four lines",
        node_result=FunctionExecutionResult(
            function_name="is_completed_order",
            status=ExecutionStatus.FAILED,
            duration_ms=110,
            error_message=(
                "line one\nline two\nline three\nline four\nline five should not appear"
            ),
        ),
        expected_fragments=(
            "error     line one",
            "          line two",
            "          line three",
            "          line four...",
        ),
        unexpected_fragments=("line five should not appear",),
    ),
]

BUILD_PROGRESS_ACTIVE_SPINNER_TEST_CASES: list[BuildProgressActiveSpinnerTestCase] = [
    BuildProgressActiveSpinnerTestCase(
        description="active function row uses spinner glyph instead of ellipsis",
        node_name="is_completed_order",
        node_type="function",
        expected_fragments=("function", "is_completed_order", "⠋"),
        unexpected_fragments=("...",),
    ),
    BuildProgressActiveSpinnerTestCase(
        description="active view row uses spinner glyph instead of ellipsis",
        node_name="stg_customers",
        node_type=MaterializationType.VIEW,
        expected_fragments=("view", "stg_customers", "⠋"),
        unexpected_fragments=("...",),
    ),
    BuildProgressActiveSpinnerTestCase(
        description="active snapshot row uses snapshot resource type",
        node_name="customer_snapshot",
        node_type=MaterializationType.SNAPSHOT,
        expected_fragments=("snapshot", "customer_snapshot", "⠋"),
        unexpected_fragments=("table",),
    ),
]


@pytest.mark.parametrize(
    "test_case",
    [
        NestedProgressChildRowsTestCase(
            description="completed item renders aligned child check rows without truncation",
            item_name="test_fact_orders",
            name_width=len("assertion line_totals_are_non_negative"),
            expected_fragments=(
                "test      test_fact_orders",
                "check   expected fact_orders",
                "check   assertion line_totals_are_non_negative",
                "expected fact_orders                               PASS",
            ),
            unexpected_fragments=("...",),
        )
    ],
    ids=["completed item renders aligned child check rows without truncation"],
)
def test_given_child_rows_when_completing_nested_progress_then_renders_aligned_checks(
    test_case: NestedProgressChildRowsTestCase,
) -> None:
    stream: StringIO = StringIO()
    callbacks: NestedCommandProgressCallbacks = NestedCommandProgressCallbacks(
        total=1,
        label="test",
        stream=stream,
        use_color=False,
        name_width=test_case.name_width,
    )

    callbacks.on_item_start(group_name="fact_orders", item_name=test_case.item_name)
    callbacks.on_item_complete(
        group_name="fact_orders",
        item_name=test_case.item_name,
        status_text="PASS",
        child_rows=(
            NestedProgressChildRow(
                label="check",
                name="expected fact_orders",
                status_text="PASS",
            ),
            NestedProgressChildRow(
                label="check",
                name="assertion line_totals_are_non_negative",
                status_text="PASS",
            ),
        ),
    )
    output: str = stream.getvalue()

    expected_fragment: str
    for expected_fragment in test_case.expected_fragments:
        assert expected_fragment in output
    unexpected_fragment: str
    for unexpected_fragment in test_case.unexpected_fragments:
        assert unexpected_fragment not in output


@pytest.mark.parametrize(
    "test_case",
    AUDIT_AGGREGATION_TEST_CASES,
    ids=[case.description for case in AUDIT_AGGREGATION_TEST_CASES],
)
def test_given_audit_results_when_aggregating_then_produces_expected_entries(
    test_case: AuditAggregationTestCase,
) -> None:
    entries: list[_AuditDisplayEntry] = _aggregate_audit_results(test_case.audit_results)

    assert len(entries) == test_case.expected_entry_count

    idx: int
    for idx in range(test_case.expected_entry_count):
        assert entries[idx].label == test_case.expected_labels[idx], (
            f"entry {idx}: expected label {test_case.expected_labels[idx]!r}, "
            f"got {entries[idx].label!r}"
        )
        assert entries[idx].outcome == test_case.expected_outcomes[idx], (
            f"entry {idx}: expected outcome {test_case.expected_outcomes[idx]!r}, "
            f"got {entries[idx].outcome!r}"
        )
        assert entries[idx].batch_total == test_case.expected_batch_totals[idx], (
            f"entry {idx}: expected batch_total {test_case.expected_batch_totals[idx]}, "
            f"got {entries[idx].batch_total}"
        )
        assert entries[idx].batch_pass == test_case.expected_batch_passes[idx], (
            f"entry {idx}: expected batch_pass {test_case.expected_batch_passes[idx]}, "
            f"got {entries[idx].batch_pass}"
        )


@pytest.mark.parametrize(
    "test_case",
    BUILD_FOOTER_TEST_CASES,
    ids=[case.description for case in BUILD_FOOTER_TEST_CASES],
)
def test_given_failed_resource_result_when_formatting_footer_then_includes_error(
    test_case: BuildFooterTestCase,
) -> None:
    footer: str = format_build_footer(result=test_case.result, elapsed=1.25, use_color=False)

    expected_fragment: str
    for expected_fragment in test_case.expected_fragments:
        assert expected_fragment in footer
    unexpected_fragment: str
    for unexpected_fragment in test_case.unexpected_fragments:
        assert unexpected_fragment not in footer


@pytest.mark.parametrize(
    "test_case",
    BUILD_PROGRESS_FAILURE_OUTPUT_TEST_CASES,
    ids=[case.description for case in BUILD_PROGRESS_FAILURE_OUTPUT_TEST_CASES],
)
def test_given_failed_top_level_node_when_reporting_progress_then_writes_error_detail_below_row(
    test_case: BuildProgressFailureOutputTestCase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stream: StringIO = StringIO()
    monkeypatch.setattr("sys.stdout", stream)
    callbacks: BuildProgressCallbacks = BuildProgressCallbacks(
        plan=PlanOutput(),
        use_color=False,
    )

    callbacks.on_node_complete(test_case.node_result)
    output: str = stream.getvalue()

    expected_fragment: str
    for expected_fragment in test_case.expected_fragments:
        assert expected_fragment in output
    unexpected_fragment: str
    for unexpected_fragment in test_case.unexpected_fragments:
        assert unexpected_fragment not in output


@pytest.mark.parametrize(
    "test_case",
    [
        BuildProgressModelOutputTestCase(
            description="completed snapshot row shows strategy and historical shape annotation",
            node_result=ModelExecutionResult(
                model_name="customer_snapshot",
                status=ExecutionStatus.SUCCESS,
                duration_ms=120,
            ),
            plan_output=build_progress_snapshot_plan_output(
                observed_at_column="loaded_at",
                historical_input="changes",
            ),
            expected_fragments=(
                "snapshot  customer_snapshot  (timestamp, historical changes)",
                "OK",
                "0.12s",
            ),
            unexpected_fragments=("table",),
        )
    ],
    ids=["completed snapshot row shows strategy and historical shape annotation"],
)
def test_given_model_node_when_reporting_progress_then_writes_materialization_label(
    test_case: BuildProgressModelOutputTestCase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stream: StringIO = StringIO()
    monkeypatch.setattr("sys.stdout", stream)
    callbacks: BuildProgressCallbacks = BuildProgressCallbacks(
        plan=test_case.plan_output,
        use_color=False,
    )

    callbacks.on_node_complete(test_case.node_result)
    output: str = stream.getvalue()

    expected_fragment: str
    for expected_fragment in test_case.expected_fragments:
        assert expected_fragment in output
    unexpected_fragment: str
    for unexpected_fragment in test_case.unexpected_fragments:
        assert unexpected_fragment not in output


@pytest.mark.parametrize(
    "test_case",
    [
        BuildProgressSqlTestRowsTestCase(
            description="completed model renders sql unit test check rows",
            expected_fragments=(
                "test      test_fact_orders",
                "check   expected fact_orders",
                "check   assertion line_totals_are_non_negative PASS",
            ),
            unexpected_fragments=("...",),
        )
    ],
    ids=["completed model renders sql unit test check rows"],
)
def test_given_sql_unit_test_result_when_reporting_model_progress_then_writes_check_rows(
    test_case: BuildProgressSqlTestRowsTestCase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stream: StringIO = StringIO()
    monkeypatch.setattr("sys.stdout", stream)
    callbacks: BuildProgressCallbacks = BuildProgressCallbacks(
        plan=PlanOutput(),
        use_color=False,
    )

    callbacks.on_node_complete(
        SqlTestExecutionResult(
            test_name="test_fact_orders",
            outcome=SqlTestOutcome.PASS,
            step_results=(
                StepResult(model_name="fact_orders", outcome=SqlTestOutcome.PASS),
                StepResult(
                    model_name="assertion line_totals_are_non_negative",
                    outcome=SqlTestOutcome.PASS,
                ),
            ),
        )
    )
    callbacks.on_node_complete(
        ModelExecutionResult(
            model_name="fact_orders",
            status=ExecutionStatus.SUCCESS,
            duration_ms=100,
        )
    )
    output: str = stream.getvalue()

    expected_fragment: str
    for expected_fragment in test_case.expected_fragments:
        assert expected_fragment in output
    unexpected_fragment: str
    for unexpected_fragment in test_case.unexpected_fragments:
        assert unexpected_fragment not in output


class _TtyStringIO(StringIO):
    def isatty(self) -> bool:
        return True


@pytest.mark.parametrize(
    "test_case",
    BUILD_PROGRESS_ACTIVE_SPINNER_TEST_CASES,
    ids=[case.description for case in BUILD_PROGRESS_ACTIVE_SPINNER_TEST_CASES],
)
def test_given_active_top_level_node_when_reporting_progress_then_uses_spinner_glyph(
    test_case: BuildProgressActiveSpinnerTestCase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stream: _TtyStringIO = _TtyStringIO()
    monkeypatch.setattr("sys.stdout", stream)
    callbacks: BuildProgressCallbacks = BuildProgressCallbacks(
        plan=PlanOutput(),
        use_color=False,
    )

    callbacks.on_node_start(test_case.node_name, test_case.node_type)
    output: str = stream.getvalue()

    expected_fragment: str
    for expected_fragment in test_case.expected_fragments:
        assert expected_fragment in output
    unexpected_fragment: str
    for unexpected_fragment in test_case.unexpected_fragments:
        assert unexpected_fragment not in output


@pytest.mark.parametrize(
    "test_case",
    [
        BuildProgressSpinnerLifecycleTestCase(
            description="active spinner advances frames over time before completion",
            node_name="stg_orders",
            node_type=MaterializationType.VIEW,
            sleep_seconds=0.22,
            completion_duration_ms=1200,
            expected_fragments=("view", "stg_orders", "OK", "\033[?25l", "\033[?25h"),
            expected_spinner_frames=("⠋", "⠙", "⠹"),
        )
    ],
    ids=["active spinner advances frames over time before completion"],
)
def test_given_active_top_level_node_when_waiting_then_spinner_advances_frames(
    test_case: BuildProgressSpinnerLifecycleTestCase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stream: _TtyStringIO = _TtyStringIO()
    monkeypatch.setattr("sys.stdout", stream)
    callbacks: BuildProgressCallbacks = BuildProgressCallbacks(
        plan=PlanOutput(),
        use_color=False,
    )

    callbacks.on_node_start(test_case.node_name, test_case.node_type)
    time.sleep(test_case.sleep_seconds)
    callbacks.on_node_complete(
        ModelExecutionResult(
            model_name=test_case.node_name,
            status=ExecutionStatus.SUCCESS,
            duration_ms=test_case.completion_duration_ms,
        )
    )
    output: str = stream.getvalue()

    expected_fragment: str
    for expected_fragment in test_case.expected_fragments:
        assert expected_fragment in output
    spinner_frame: str
    for spinner_frame in test_case.expected_spinner_frames:
        assert spinner_frame in output
