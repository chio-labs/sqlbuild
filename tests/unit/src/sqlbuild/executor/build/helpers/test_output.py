"""Unit tests for build output formatting."""

from __future__ import annotations

import pytest

from sqlbuild.adapter.shared.models import LifeCycleEvent
from sqlbuild.adapter.shared.types import LifeCycleEventKind
from sqlbuild.compiler.auditing.types import AuditOutcome, AuditRunScope
from sqlbuild.compiler.planner.models import ModelPlanEntry, SeedPlanEntry
from sqlbuild.compiler.planner.types import (
    MaterializationType,
    PlanAction,
)
from sqlbuild.executor.build.helpers.output import format_build_output
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
from tests.unit.src.sqlbuild.executor.build.helpers._test_types import (
    BuildOutputTestCase,
    ModelPlanOverride,
)
from tests.unit.src.sqlbuild.executor.build.helpers.helpers import (
    build_audit_result,
    build_model_plan_entry,
    build_plan_output,
    build_seed_plan_entry,
)

TEST_CASES: list[BuildOutputTestCase] = [
    BuildOutputTestCase(
        description="success build shows OK status and completed successfully",
        result=BuildExecutionResult(
            status=BuildStatus.SUCCESS,
            model_results=(
                ModelExecutionResult(
                    model_name="orders",
                    status=ExecutionStatus.SUCCESS,
                    duration_ms=150,
                ),
            ),
            success_count=1,
        ),
        expected_output_fragments=(
            "1/1",
            "table",
            "orders",
            "OK",
            "0.15s",
            "Completed successfully.",
            "PASS=1",
            "FAIL=0",
        ),
    ),
    BuildOutputTestCase(
        description="snapshot model output shows strategy and historical shape annotation",
        result=BuildExecutionResult(
            status=BuildStatus.SUCCESS,
            model_results=(
                ModelExecutionResult(
                    model_name="customer_snapshot",
                    status=ExecutionStatus.SUCCESS,
                    duration_ms=150,
                ),
            ),
            success_count=1,
        ),
        model_plan_overrides=(
            ModelPlanOverride(
                name="customer_snapshot",
                materialization_type=MaterializationType.SNAPSHOT,
                action=PlanAction.SNAPSHOT,
                snapshot_strategy="check",
                observed_at_column="observed_at",
                historical_input="snapshot",
            ),
        ),
        expected_output_fragments=(
            "1/1",
            "snapshot",
            "customer_snapshot  (check, historical snapshot)",
            "OK",
            "0.15s",
        ),
        expected_absent_fragments=("table",),
    ),
    BuildOutputTestCase(
        description="failed model shows FAIL status with phase and failure detail",
        result=BuildExecutionResult(
            status=BuildStatus.FAILED,
            model_results=(
                ModelExecutionResult(
                    model_name="orders",
                    status=ExecutionStatus.FAILED,
                    failed_phase=ExecutionPhase.STAGING,
                    duration_ms=50,
                    error_code="R002",
                    error_message="Table raw_orders does not exist",
                ),
            ),
            failure_count=1,
        ),
        expected_output_fragments=(
            "1/1",
            "FAIL",
            "staging",
            "Completed with errors.",
            "FAIL=1",
            "Failures:",
            "orders  (staging)",
            "error[R002]: Table raw_orders does not exist",
            "Table raw_orders does not exist",
        ),
    ),
    BuildOutputTestCase(
        description="colorized failed model shows styled coded error and help",
        result=BuildExecutionResult(
            status=BuildStatus.FAILED,
            model_results=(
                ModelExecutionResult(
                    model_name="orders",
                    status=ExecutionStatus.FAILED,
                    failed_phase=ExecutionPhase.PROMOTION,
                    error_code="R007",
                    error_help="inspect staging relation",
                    error_message="promotion failed",
                ),
            ),
            failure_count=1,
        ),
        use_color=True,
        expected_output_fragments=(
            "\033[31m\033[1merror[R007]:\033[0m promotion failed",
            "\033[2m= help:\033[0m inspect staging relation",
        ),
    ),
    BuildOutputTestCase(
        description="skipped model shows SKIP with no duration",
        result=BuildExecutionResult(
            status=BuildStatus.FAILED,
            model_results=(
                ModelExecutionResult(
                    model_name="upstream",
                    status=ExecutionStatus.FAILED,
                    failed_phase=ExecutionPhase.STAGING,
                    duration_ms=10,
                    error_message="bad SQL",
                ),
                ModelExecutionResult(
                    model_name="downstream",
                    status=ExecutionStatus.SKIPPED,
                ),
            ),
            failure_count=1,
            skipped_count=1,
        ),
        expected_output_fragments=(
            "1/2",
            "upstream",
            "FAIL",
            "2/2",
            "downstream",
            "SKIP",
            "SKIP=1",
        ),
        expected_absent_fragments=("downstream" + "0.00s",),
    ),
    BuildOutputTestCase(
        description="warn audit shows WARN with row count in output and warnings section",
        result=BuildExecutionResult(
            status=BuildStatus.SUCCESS,
            model_results=(
                ModelExecutionResult(
                    model_name="orders",
                    status=ExecutionStatus.SUCCESS,
                    duration_ms=100,
                    audit_results=(
                        build_audit_result(
                            name="not_null",
                            outcome=AuditOutcome.WARN,
                            row_count=3,
                            column_name="email",
                        ),
                    ),
                ),
            ),
            success_count=1,
            warning_count=1,
        ),
        expected_output_fragments=(
            "WARN",
            "3 rows",
            "Completed with warnings.",
            "WARN=1",
            "Warnings:",
            "not_null (email) returned 3 rows",
        ),
    ),
    BuildOutputTestCase(
        description="passing audit shows PASS with no row count",
        result=BuildExecutionResult(
            status=BuildStatus.SUCCESS,
            model_results=(
                ModelExecutionResult(
                    model_name="orders",
                    status=ExecutionStatus.SUCCESS,
                    duration_ms=100,
                    audit_results=(
                        build_audit_result(
                            name="not_null",
                            outcome=AuditOutcome.PASS,
                            column_name="id",
                        ),
                    ),
                ),
            ),
            success_count=1,
        ),
        expected_output_fragments=(
            "audit",
            "not_null (id)",
            "PASS",
        ),
        expected_absent_fragments=(
            "Warnings:",
            "Failures:",
        ),
    ),
    BuildOutputTestCase(
        description="seed line shows seed type and OK status",
        result=BuildExecutionResult(
            status=BuildStatus.SUCCESS,
            seed_results=(
                SeedExecutionResult(
                    seed_name="country_codes",
                    status=ExecutionStatus.SUCCESS,
                    duration_ms=20,
                ),
            ),
            success_count=1,
        ),
        expected_output_fragments=(
            "1/1",
            "seed",
            "country_codes",
            "OK",
            "0.02s",
        ),
    ),
    BuildOutputTestCase(
        description="failed seed shows failure detail",
        result=BuildExecutionResult(
            status=BuildStatus.FAILED,
            seed_results=(
                SeedExecutionResult(
                    seed_name="waffle_types",
                    status=ExecutionStatus.FAILED,
                    duration_ms=20,
                    error_message="failed to load seed CSV: invalid input syntax",
                ),
            ),
            failure_count=1,
        ),
        expected_output_fragments=(
            "seed",
            "waffle_types",
            "FAIL",
            "Failures:",
            "waffle_types  (seed)",
            "failed to load seed CSV: invalid input syntax",
        ),
    ),
    BuildOutputTestCase(
        description="failed function shows failure detail",
        result=BuildExecutionResult(
            status=BuildStatus.FAILED,
            function_results=(
                FunctionExecutionResult(
                    function_name="is_completed_order",
                    status=ExecutionStatus.FAILED,
                    error_message="function target could not be qualified",
                ),
            ),
            failure_count=1,
        ),
        expected_output_fragments=(
            "FAIL=1",
            "Failures:",
            "is_completed_order  (function)",
            "function target could not be qualified",
        ),
    ),
    BuildOutputTestCase(
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
        expected_output_fragments=(
            "Completed with warnings.",
            "PASS=1",
            "WARN=1",
            "Warnings:",
            "is_completed_order_py  (function)",
            "fingerprint write skipped",
        ),
    ),
    BuildOutputTestCase(
        description="view model shows view type",
        result=BuildExecutionResult(
            status=BuildStatus.SUCCESS,
            model_results=(
                ModelExecutionResult(
                    model_name="stg_orders",
                    status=ExecutionStatus.SUCCESS,
                    duration_ms=10,
                ),
            ),
            success_count=1,
        ),
        model_plan_overrides=(
            ModelPlanOverride(
                name="stg_orders",
                materialization_type=MaterializationType.VIEW,
                action=PlanAction.CREATE_VIEW,
            ),
        ),
        expected_output_fragments=(
            "view",
            "stg_orders",
            "OK",
        ),
    ),
    BuildOutputTestCase(
        description="header includes target and concurrency",
        result=BuildExecutionResult(status=BuildStatus.SUCCESS),
        target="prod",
        concurrency=4,
        expected_output_fragments=(
            "sqb build",
            "target: prod",
            "concurrency: 4",
        ),
    ),
    BuildOutputTestCase(
        description="counter counts seeds and models together",
        result=BuildExecutionResult(
            status=BuildStatus.SUCCESS,
            seed_results=(
                SeedExecutionResult(
                    seed_name="seed_a",
                    status=ExecutionStatus.SUCCESS,
                    duration_ms=10,
                ),
            ),
            model_results=(
                ModelExecutionResult(
                    model_name="model_a",
                    status=ExecutionStatus.SUCCESS,
                    duration_ms=100,
                ),
                ModelExecutionResult(
                    model_name="model_b",
                    status=ExecutionStatus.SUCCESS,
                    duration_ms=100,
                ),
            ),
            success_count=3,
        ),
        expected_output_fragments=(
            "1/3",
            "seed_a",
            "2/3",
            "model_a",
            "3/3",
            "model_b",
            "TOTAL=3",
        ),
    ),
    BuildOutputTestCase(
        description="failed test shows in summary counts as FAIL",
        result=BuildExecutionResult(
            status=BuildStatus.FAILED,
            model_results=(
                ModelExecutionResult(
                    model_name="orders",
                    status=ExecutionStatus.SKIPPED,
                ),
            ),
            test_results=(
                SqlTestExecutionResult(
                    test_name="test_orders",
                    outcome=SqlTestOutcome.FAIL,
                    step_results=(
                        StepResult(
                            model_name="orders",
                            outcome=SqlTestOutcome.FAIL,
                            mismatched_row_count=1,
                        ),
                    ),
                    error_message="test 'test_orders' failed for models: orders",
                ),
            ),
            failure_count=1,
            skipped_count=1,
        ),
        expected_output_fragments=(
            "SKIP",
            "expect expected orders",
            "FAIL  1 mismatched",
            "Completed with errors.",
            "FAIL=1",
            "SKIP=1",
            "Failures:",
            "test_orders  (test)",
        ),
    ),
    BuildOutputTestCase(
        description="unit test expectation rows show assertion names",
        result=BuildExecutionResult(
            status=BuildStatus.SUCCESS,
            model_results=(
                ModelExecutionResult(
                    model_name="fact_orders",
                    status=ExecutionStatus.SUCCESS,
                    duration_ms=100,
                ),
            ),
            test_results=(
                SqlTestExecutionResult(
                    test_name="test_fact_orders",
                    outcome=SqlTestOutcome.PASS,
                    step_results=(
                        StepResult(
                            model_name="fact_orders",
                            outcome=SqlTestOutcome.PASS,
                        ),
                        StepResult(
                            model_name="assertion line_totals_are_non_negative",
                            outcome=SqlTestOutcome.PASS,
                        ),
                    ),
                ),
            ),
            success_count=2,
        ),
        expected_output_fragments=(
            "test   test_fact_orders",
            "expect expected fact_orders",
            "expect assertion line_totals_are_non_negative PASS",
        ),
    ),
    BuildOutputTestCase(
        description="counter excludes tests from total count",
        result=BuildExecutionResult(
            status=BuildStatus.SUCCESS,
            seed_results=(
                SeedExecutionResult(
                    seed_name="seed_data",
                    status=ExecutionStatus.SUCCESS,
                    duration_ms=10,
                ),
            ),
            model_results=(
                ModelExecutionResult(
                    model_name="orders",
                    status=ExecutionStatus.SUCCESS,
                    duration_ms=100,
                ),
            ),
            test_results=(
                SqlTestExecutionResult(
                    test_name="test_orders",
                    outcome=SqlTestOutcome.PASS,
                    step_results=(
                        StepResult(
                            model_name="orders",
                            outcome=SqlTestOutcome.PASS,
                        ),
                    ),
                ),
            ),
            success_count=2,
        ),
        expected_output_fragments=(
            "1/2",
            "2/2",
            "TOTAL=3",
        ),
        expected_absent_fragments=(
            "3/2",
            "1/3",
            "2/3",
            "3/3",
        ),
    ),
    BuildOutputTestCase(
        description="staging retained info shows in failure details",
        result=BuildExecutionResult(
            status=BuildStatus.FAILED,
            model_results=(
                ModelExecutionResult(
                    model_name="orders",
                    status=ExecutionStatus.FAILED,
                    failed_phase=ExecutionPhase.AUDIT,
                    duration_ms=200,
                    error_message=(
                        "final audit for 'orders' failed before replacing target table "
                        "with severity level: error"
                    ),
                    staging_relation="main.orders__staging",
                ),
            ),
            failure_count=1,
        ),
        expected_output_fragments=(
            "Failures:",
            "orders  (audit)",
            "final audit for 'orders' failed before replacing target table",
            "staging table kept for inspection: main.orders__staging",
        ),
    ),
    BuildOutputTestCase(
        description="elapsed time appears in summary",
        result=BuildExecutionResult(status=BuildStatus.SUCCESS),
        elapsed_seconds=2.34,
        expected_output_fragments=("(2.34s)",),
    ),
    BuildOutputTestCase(
        description="delta_and_final audits show phase labels and batch count",
        result=BuildExecutionResult(
            status=BuildStatus.SUCCESS,
            model_results=(
                ModelExecutionResult(
                    model_name="orders",
                    status=ExecutionStatus.SUCCESS,
                    duration_ms=100,
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
                            run_scope_phase=AuditRunScope.FINAL,
                        ),
                    ),
                ),
            ),
            success_count=1,
        ),
        expected_output_fragments=(
            "audit (d)",
            "audit (f)",
            "not_null (id)",
            "2/2",
        ),
    ),
    BuildOutputTestCase(
        description="final-only audits show plain audit label without batch count",
        result=BuildExecutionResult(
            status=BuildStatus.SUCCESS,
            model_results=(
                ModelExecutionResult(
                    model_name="orders",
                    status=ExecutionStatus.SUCCESS,
                    duration_ms=100,
                    audit_results=(
                        build_audit_result(
                            name="not_null",
                            outcome=AuditOutcome.PASS,
                            column_name="id",
                        ),
                    ),
                ),
            ),
            success_count=1,
        ),
        expected_output_fragments=(
            "audit",
            "not_null (id)",
            "PASS",
        ),
        expected_absent_fragments=(
            "audit (d)",
            "audit (f)",
        ),
    ),
    BuildOutputTestCase(
        description="verbose mode shows executed lifecycle SQL and audit SQL",
        result=BuildExecutionResult(
            status=BuildStatus.SUCCESS,
            model_results=(
                ModelExecutionResult(
                    model_name="orders",
                    status=ExecutionStatus.SUCCESS,
                    duration_ms=100,
                    lifecycle_events=(
                        LifeCycleEvent(
                            kind=LifeCycleEventKind.SQL,
                            content="DROP TABLE IF EXISTS main.orders__staging",
                        ),
                        LifeCycleEvent(
                            kind=LifeCycleEventKind.LOG,
                            content="building partition 2024-01-01",
                        ),
                        LifeCycleEvent(
                            kind=LifeCycleEventKind.SQL,
                            content="CREATE OR REPLACE TABLE main.orders__staging AS SELECT 1",
                        ),
                    ),
                    audit_results=(
                        build_audit_result(
                            name="not_null",
                            outcome=AuditOutcome.PASS,
                            column_name="id",
                        ),
                    ),
                ),
            ),
            success_count=1,
        ),
        verbose=True,
        expected_output_fragments=(
            "DROP TABLE IF EXISTS main.orders__staging",
            "log  building partition 2024-01-01",
            "CREATE OR REPLACE TABLE main.orders__staging AS SELECT 1;",
            "SELECT 1;",
            "orders",
            "OK",
        ),
        expected_absent_fragments=("CREATE TABLE main.orders AS SELECT 1",),
    ),
    BuildOutputTestCase(
        description="non-verbose mode omits model DDL",
        result=BuildExecutionResult(
            status=BuildStatus.SUCCESS,
            model_results=(
                ModelExecutionResult(
                    model_name="orders",
                    status=ExecutionStatus.SUCCESS,
                    duration_ms=100,
                ),
            ),
            success_count=1,
        ),
        verbose=False,
        expected_output_fragments=(
            "orders",
            "OK",
        ),
        expected_absent_fragments=("CREATE TABLE",),
    ),
    BuildOutputTestCase(
        description="colorized verbose mode shows lifecycle log messages in muted blue",
        result=BuildExecutionResult(
            status=BuildStatus.SUCCESS,
            model_results=(
                ModelExecutionResult(
                    model_name="orders",
                    status=ExecutionStatus.SUCCESS,
                    duration_ms=100,
                    lifecycle_events=(
                        LifeCycleEvent(
                            kind=LifeCycleEventKind.LOG,
                            content="building partition 2024-01-01",
                        ),
                    ),
                ),
            ),
            success_count=1,
        ),
        verbose=True,
        use_color=True,
        expected_output_fragments=("\033[34m\033[2m    log  building partition 2024-01-01\033[0m",),
    ),
]


@pytest.mark.parametrize(
    "test_case",
    TEST_CASES,
    ids=[case.description for case in TEST_CASES],
)
def test_given_build_result_when_formatting_output_then_contains_expected_fragments(
    test_case: BuildOutputTestCase,
) -> None:
    override_map: dict[str, ModelPlanOverride] = {o.name: o for o in test_case.model_plan_overrides}
    plan_entries: list[ModelPlanEntry] = []
    model_result: ModelExecutionResult
    for model_result in test_case.result.model_results:
        override: ModelPlanOverride | None = override_map.get(model_result.model_name)
        mat_type: MaterializationType = (
            override.materialization_type if override else MaterializationType.TABLE
        )
        action: PlanAction = override.action if override else PlanAction.CREATE_TABLE
        plan_entries.append(
            build_model_plan_entry(
                name=model_result.model_name,
                materialization_type=mat_type,
                action=action,
                snapshot_strategy=override.snapshot_strategy if override else None,
                observed_at_column=override.observed_at_column if override else None,
                historical_input=override.historical_input if override else None,
            )
        )

    seed_entries: tuple[SeedPlanEntry, ...] = tuple(
        build_seed_plan_entry(name=sr.seed_name) for sr in test_case.result.seed_results
    )

    plan: object = build_plan_output(
        model_entries=tuple(plan_entries),
        seed_entries=seed_entries,
    )

    output: str = format_build_output(
        result=test_case.result,
        plan=plan,
        target=test_case.target,
        concurrency=test_case.concurrency,
        elapsed_seconds=test_case.elapsed_seconds,
        use_color=test_case.use_color,
        verbose=test_case.verbose,
    )

    expected_fragment: str
    for expected_fragment in test_case.expected_output_fragments:
        assert expected_fragment in output, (
            f"Expected fragment {expected_fragment!r} not found in output:\n{output}"
        )

    absent_fragment: str
    for absent_fragment in test_case.expected_absent_fragments:
        assert absent_fragment not in output, (
            f"Fragment {absent_fragment!r} should not be in output:\n{output}"
        )
