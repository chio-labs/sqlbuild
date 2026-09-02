from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from typing import cast

import pytest

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.cli.commands._helpers.freshness.source_freshness import (
    append_eligible_direct_source_freshness_records,
)
from sqlbuild.compiler.planner.models import PlanOutput
from sqlbuild.compiler.source_freshness.models import (
    DirectSourceFreshnessPlanningResult,
    DirectSourceFreshnessPropagationResult,
)
from sqlbuild.cost.classes.cost_context import CostContext
from sqlbuild.cost.models import CostResourceContext
from sqlbuild.executor.build.models import BuildExecutionResult
from sqlbuild.executor.build.types import BuildStatus
from sqlbuild.executor.run.models import ModelExecutionResult
from sqlbuild.executor.scheduling.types import ExecutionStatus
from sqlbuild.observability import EventDispatcher, dispatcher_scope, invocation_scope
from tests.unit.src.sqlbuild.cli.commands._helpers._test_types import (
    SourceFreshnessAppendEligibilityTestCase,
)
from tests.unit.src.sqlbuild.cli.commands._helpers.helpers import (
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
            expected_lifecycle_order=("operation_started", "connect", "operation_completed"),
        ),
        SourceFreshnessAppendEligibilityTestCase(
            description="does not append when affected selected model fails",
            model_statuses={"orders": ExecutionStatus.FAILED},
            expected_insert_count=0,
            expected_lifecycle_order=(),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_source_freshness_observation_when_appending_then_requires_successful_models(
    test_case: SourceFreshnessAppendEligibilityTestCase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter: RecordingAdapter = RecordingAdapter()
    lifecycle_order: list[str] = []
    dispatcher: EventDispatcher = EventDispatcher()
    dispatcher.subscribe_lifecycle(
        subscriber=lambda event: lifecycle_order.append(event.event_type), accepts_opaque=False
    )
    original_connect: Callable[[dict[str, object]], object] = adapter.connect

    def connect_after_start(config: dict[str, object]) -> object:
        lifecycle_order.append("connect")
        return original_connect(config)

    monkeypatch.setattr(adapter, "connect", connect_after_start)

    with invocation_scope("freshness-invocation"), dispatcher_scope(dispatcher):
        append_eligible_direct_source_freshness_records(
            plan=PlanOutput(
                model_entries=(model_entry("orders"),),
                source_freshness=DirectSourceFreshnessPlanningResult(
                    observed_records=(source_freshness_record(),),
                    changed_identities=frozenset({source_freshness_identity()}),
                    propagation=DirectSourceFreshnessPropagationResult(
                        changed_source_model_names={
                            source_freshness_identity(): frozenset({"orders"})
                        },
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
    assert tuple(lifecycle_order) == test_case.expected_lifecycle_order


@pytest.mark.parametrize(
    "test_case",
    [
        SourceFreshnessAppendEligibilityTestCase(
            description="uses adapter-rendered source freshness state relation",
            model_statuses={"orders": ExecutionStatus.SUCCESS},
            expected_insert_count=1,
            expected_lifecycle_order=(),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_eligible_source_freshness_when_appending_then_uses_adapter_rendered_state_relation(
    test_case: SourceFreshnessAppendEligibilityTestCase,
) -> None:
    adapter: RecordingAdapter = RecordingAdapter()

    with CostContext.scope(
        run_id="run-1",
        resource_type="run",
        resource_name="dev",
        phase="build",
    ):
        append_eligible_direct_source_freshness_records(
            plan=PlanOutput(
                model_entries=(model_entry("orders"),),
                source_freshness=DirectSourceFreshnessPlanningResult(
                    observed_records=(source_freshness_record(),),
                    changed_identities=frozenset({source_freshness_identity()}),
                    propagation=DirectSourceFreshnessPropagationResult(
                        changed_source_model_names={
                            source_freshness_identity(): frozenset({"orders"})
                        },
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
    assert adapter.executed_sql[-1].strip().startswith("INSERT")
    insert_context: CostResourceContext | None = adapter.cost_contexts[-1]
    assert insert_context is not None
    assert insert_context.resource_type == "source"
    assert insert_context.resource_name == "raw_orders"
    assert insert_context.phase == "freshness_finalization"
    assert insert_context.attempt == 1


@pytest.mark.parametrize(
    "test_case",
    [
        SourceFreshnessAppendEligibilityTestCase(
            description="persists plan-time observation with successful build run id",
            model_statuses={"orders": ExecutionStatus.SUCCESS},
            expected_insert_count=1,
            expected_lifecycle_order=(),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_eligible_source_freshness_when_appending_then_reuses_plan_time_observation(
    test_case: SourceFreshnessAppendEligibilityTestCase,
) -> None:
    adapter: RecordingAdapter = RecordingAdapter()

    append_eligible_direct_source_freshness_records(
        plan=PlanOutput(
            model_entries=(model_entry("orders"),),
            source_freshness=DirectSourceFreshnessPlanningResult(
                observed_records=(
                    source_freshness_record(
                        run_id="planning-run",
                        data_version="plan-time-version",
                        data_version_hash="plan-time-hash",
                    ),
                ),
                changed_identities=frozenset({source_freshness_identity()}),
                propagation=DirectSourceFreshnessPropagationResult(
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

    sql_by_insert_status: defaultdict[bool, list[str]] = defaultdict(list)
    for sql in adapter.executed_sql:
        sql_by_insert_status[sql.strip().startswith("INSERT")].append(sql)
    insert_sql: str = next(iter(sql_by_insert_status[True]))
    assert adapter.insert_count == test_case.expected_insert_count
    assert "successful-build-run" in insert_sql
    assert "planning-run" not in insert_sql
    assert "plan-time-version" in insert_sql
    assert "plan-time-hash" in insert_sql
