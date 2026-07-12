from __future__ import annotations

from typing import cast

import pytest

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.cli.commands.helpers.freshness.source_freshness import (
    append_eligible_standard_source_freshness_records,
)
from sqlbuild.compiler.planner.models import PlanOutput
from sqlbuild.compiler.source_freshness.models import (
    StandardSourceFreshnessPlanningResult,
    StandardSourceFreshnessPropagationResult,
)
from sqlbuild.executor.build.models import BuildExecutionResult
from sqlbuild.executor.build.types import BuildStatus
from sqlbuild.executor.run.models import ModelExecutionResult
from sqlbuild.executor.types import ExecutionStatus
from tests.unit.src.sqlbuild.cli.commands.helpers._test_types import (
    SourceFreshnessAppendEligibilityTestCase,
)
from tests.unit.src.sqlbuild.cli.commands.helpers.helpers import (
    RecordingAdapter,
    model_entry,
    source_freshness_identity,
    source_freshness_record,
)


@pytest.mark.parametrize(
    "test_case",
    [
        SourceFreshnessAppendEligibilityTestCase(
            description="appends when all affected selected models succeed",
            model_statuses={"orders": ExecutionStatus.SUCCESS},
            expected_insert_count=1,
        ),
        SourceFreshnessAppendEligibilityTestCase(
            description="does not append when affected selected model fails",
            model_statuses={"orders": ExecutionStatus.FAILED},
            expected_insert_count=0,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_source_freshness_observation_when_appending_then_requires_successful_models(
    test_case: SourceFreshnessAppendEligibilityTestCase,
) -> None:
    adapter: RecordingAdapter = RecordingAdapter()

    append_eligible_standard_source_freshness_records(
        plan=PlanOutput(
            model_entries=(model_entry("orders"),),
            source_freshness=StandardSourceFreshnessPlanningResult(
                observed_records=(source_freshness_record(),),
                changed_identities=frozenset({source_freshness_identity()}),
                propagation=StandardSourceFreshnessPropagationResult(
                    changed_source_model_names={source_freshness_identity(): frozenset({"orders"})},
                    stale_model_names=frozenset({"orders"}),
                ),
            ),
        ),
        result=BuildExecutionResult(
            status=BuildStatus.SUCCESS,
            model_results=tuple(
                ModelExecutionResult(model_name=model_name, status=status)
                for model_name, status in test_case.model_statuses.items()
            ),
        ),
        adapter=cast(BaseAdapter, adapter),
        connection_config={},
        run_id="run-1",
    )

    assert adapter.insert_count == test_case.expected_insert_count


@pytest.mark.parametrize(
    "test_case",
    [
        SourceFreshnessAppendEligibilityTestCase(
            description="uses adapter-rendered source freshness state relation",
            model_statuses={"orders": ExecutionStatus.SUCCESS},
            expected_insert_count=1,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_eligible_source_freshness_when_appending_then_uses_adapter_rendered_state_relation(
    test_case: SourceFreshnessAppendEligibilityTestCase,
) -> None:
    adapter: RecordingAdapter = RecordingAdapter()

    append_eligible_standard_source_freshness_records(
        plan=PlanOutput(
            model_entries=(model_entry("orders"),),
            source_freshness=StandardSourceFreshnessPlanningResult(
                observed_records=(source_freshness_record(),),
                changed_identities=frozenset({source_freshness_identity()}),
                propagation=StandardSourceFreshnessPropagationResult(
                    changed_source_model_names={source_freshness_identity(): frozenset({"orders"})},
                    stale_model_names=frozenset({"orders"}),
                ),
            ),
        ),
        result=BuildExecutionResult(
            status=BuildStatus.SUCCESS,
            model_results=tuple(
                ModelExecutionResult(model_name=model_name, status=status)
                for model_name, status in test_case.model_statuses.items()
            ),
        ),
        adapter=cast(BaseAdapter, adapter),
        connection_config={},
        run_id="run-1",
    )

    assert adapter.insert_count == test_case.expected_insert_count
    assert any("main._sqlbuild_source_freshness" in sql for sql in adapter.executed_sql)


@pytest.mark.parametrize(
    "test_case",
    [
        SourceFreshnessAppendEligibilityTestCase(
            description="persists plan-time observation with successful build run id",
            model_statuses={"orders": ExecutionStatus.SUCCESS},
            expected_insert_count=1,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_eligible_source_freshness_when_appending_then_reuses_plan_time_observation(
    test_case: SourceFreshnessAppendEligibilityTestCase,
) -> None:
    adapter: RecordingAdapter = RecordingAdapter()

    append_eligible_standard_source_freshness_records(
        plan=PlanOutput(
            model_entries=(model_entry("orders"),),
            source_freshness=StandardSourceFreshnessPlanningResult(
                observed_records=(
                    source_freshness_record(
                        run_id="planning-run",
                        data_version="plan-time-version",
                        data_version_hash="plan-time-hash",
                    ),
                ),
                changed_identities=frozenset({source_freshness_identity()}),
                propagation=StandardSourceFreshnessPropagationResult(
                    changed_source_model_names={source_freshness_identity(): frozenset({"orders"})},
                    stale_model_names=frozenset({"orders"}),
                ),
            ),
        ),
        result=BuildExecutionResult(
            status=BuildStatus.SUCCESS,
            model_results=tuple(
                ModelExecutionResult(model_name=model_name, status=status)
                for model_name, status in test_case.model_statuses.items()
            ),
        ),
        adapter=cast(BaseAdapter, adapter),
        connection_config={},
        run_id="successful-build-run",
    )

    insert_sql: str = next(sql for sql in adapter.executed_sql if sql.strip().startswith("INSERT"))
    assert adapter.insert_count == test_case.expected_insert_count
    assert "successful-build-run" in insert_sql
    assert "planning-run" not in insert_sql
    assert "plan-time-version" in insert_sql
    assert "plan-time-hash" in insert_sql
