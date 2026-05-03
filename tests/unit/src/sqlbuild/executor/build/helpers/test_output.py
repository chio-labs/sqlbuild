"""Unit tests for build output formatting."""

from __future__ import annotations

import pytest

from sqlbuild.compiler.auditing.types import AuditOutcome
from sqlbuild.compiler.planner.models import ModelPlanEntry, SeedPlanEntry
from sqlbuild.compiler.planner.types import (
    MaterializationType,
    PlanAction,
)
from sqlbuild.executor.build.helpers.output import format_build_output
from sqlbuild.executor.build.models import BuildExecutionResult, SeedExecutionResult
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
        description="failed model shows FAIL status with phase and failure detail",
        result=BuildExecutionResult(
            status=BuildStatus.FAILED,
            model_results=(
                ModelExecutionResult(
                    model_name="orders",
                    status=ExecutionStatus.FAILED,
                    failed_phase=ExecutionPhase.STAGING,
                    duration_ms=50,
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
            "Table raw_orders does not exist",
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
            "Completed with errors.",
            "FAIL=1",
            "SKIP=1",
            "Failures:",
            "test_orders  (test)",
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
                    error_message="pre-promotion audit failed",
                    staging_relation="main.orders__staging",
                ),
            ),
            failure_count=1,
        ),
        expected_output_fragments=(
            "Failures:",
            "orders  (audit)",
            "pre-promotion audit failed",
            "staging retained as main.orders__staging",
        ),
    ),
    BuildOutputTestCase(
        description="elapsed time appears in summary",
        result=BuildExecutionResult(status=BuildStatus.SUCCESS),
        elapsed_seconds=2.34,
        expected_output_fragments=("(2.34s)",),
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
        use_color=False,
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
