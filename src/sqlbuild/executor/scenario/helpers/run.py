"""Helpers for running a planned scenario."""

from __future__ import annotations

from typing import Any

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.compiler.planner.models import ScenarioExecutionPlan, ScenarioRelationMap
from sqlbuild.executor.build.models import SeedExecutionResult
from sqlbuild.executor.run.models import ModelExecutionResult
from sqlbuild.executor.scenario.helpers.expectations import (
    execute_scenario_assertion_expectations,
    execute_scenario_expected_expectations,
)
from sqlbuild.executor.scenario.helpers.fixtures import (
    execute_scenario_fixtures,
    execute_scenario_seed_entries,
)
from sqlbuild.executor.scenario.helpers.model_execution import execute_scenario_models
from sqlbuild.executor.scenario.main.cleanup import execute_scenario_cleanup
from sqlbuild.executor.scenario.models import (
    ScenarioAssertionExpectationExecutionResult,
    ScenarioCleanupExecutionResult,
    ScenarioExpectedExpectationExecutionResult,
    ScenarioFixtureExecutionResult,
    ScenarioRunResult,
)
from sqlbuild.executor.shared.types import ExecutionStatus
from sqlbuild.shared.constants import SCENARIO_EXEC_CLEANUP_FAILED


def execute_scenario_run_steps(
    *,
    scenario_plan: ScenarioExecutionPlan,
    adapter: BaseAdapter,
    connection: Any,
    run_id: str,
    retain: bool,
) -> ScenarioRunResult:
    """Execute a planned scenario and apply cleanup policy."""

    prepare_result: ScenarioCleanupExecutionResult = execute_scenario_cleanup(
        scenario_plan=scenario_plan,
        adapter=adapter,
        connection=connection,
    )
    if prepare_result.status == ExecutionStatus.FAILED:
        return _scenario_failure(
            scenario_name=scenario_plan.name,
            relation_map=scenario_plan.relation_plan.relation_map,
            retained=retain,
            prepare_cleanup_result=prepare_result,
            error_code=prepare_result.error_code,
            error_help=prepare_result.error_help,
            error_message=prepare_result.error_message,
        )

    fixture_results: tuple[ScenarioFixtureExecutionResult, ...] = execute_scenario_fixtures(
        scenario_name=scenario_plan.name,
        fixture_plans=scenario_plan.fixture_plans,
        adapter=adapter,
        connection=connection,
    )
    if _has_failed(fixture_results):
        return _finish_scenario(
            scenario_plan=scenario_plan,
            adapter=adapter,
            connection=connection,
            retain=retain,
            prepare_cleanup_result=prepare_result,
            fixture_results=fixture_results,
            error_code=_first_error_code(fixture_results),
            error_help=_first_error_help(fixture_results),
            error_message=_first_error(fixture_results),
        )

    seed_results: tuple[SeedExecutionResult, ...] = execute_scenario_seed_entries(
        seed_entries=scenario_plan.seed_entries,
        adapter=adapter,
        connection=connection,
    )
    if _has_failed(seed_results):
        return _finish_scenario(
            scenario_plan=scenario_plan,
            adapter=adapter,
            connection=connection,
            retain=retain,
            prepare_cleanup_result=prepare_result,
            fixture_results=fixture_results,
            seed_results=seed_results,
            error_code=_first_error_code(seed_results),
            error_help=_first_error_help(seed_results),
            error_message=_first_error(seed_results),
        )

    model_results: tuple[ModelExecutionResult, ...] = execute_scenario_models(
        scenario_plan=scenario_plan,
        adapter=adapter,
        connection=connection,
        run_id=run_id,
    )
    if _has_failed(model_results):
        return _finish_scenario(
            scenario_plan=scenario_plan,
            adapter=adapter,
            connection=connection,
            retain=retain,
            prepare_cleanup_result=prepare_result,
            fixture_results=fixture_results,
            seed_results=seed_results,
            model_results=model_results,
            error_code=_first_error_code(model_results),
            error_help=_first_error_help(model_results),
            error_message=_first_error(model_results),
        )

    expected_results: tuple[ScenarioExpectedExpectationExecutionResult, ...]
    expected_results = execute_scenario_expected_expectations(
        scenario_plan=scenario_plan,
        adapter=adapter,
        connection=connection,
    )
    assertion_results: tuple[ScenarioAssertionExpectationExecutionResult, ...]
    assertion_results = execute_scenario_assertion_expectations(
        scenario_plan=scenario_plan,
        adapter=adapter,
        connection=connection,
    )
    failed_check_message: str | None = _first_error((*expected_results, *assertion_results))
    failed_check_code: str | None = _first_error_code((*expected_results, *assertion_results))
    failed_check_help: str | None = _first_error_help((*expected_results, *assertion_results))
    return _finish_scenario(
        scenario_plan=scenario_plan,
        adapter=adapter,
        connection=connection,
        retain=retain,
        prepare_cleanup_result=prepare_result,
        fixture_results=fixture_results,
        seed_results=seed_results,
        model_results=model_results,
        expected_results=expected_results,
        assertion_results=assertion_results,
        error_code=failed_check_code,
        error_help=failed_check_help,
        error_message=failed_check_message,
    )


def _finish_scenario(
    *,
    scenario_plan: ScenarioExecutionPlan,
    adapter: BaseAdapter,
    connection: Any,
    retain: bool,
    prepare_cleanup_result: ScenarioCleanupExecutionResult,
    fixture_results: tuple[ScenarioFixtureExecutionResult, ...] = (),
    seed_results: tuple[SeedExecutionResult, ...] = (),
    model_results: tuple[ModelExecutionResult, ...] = (),
    expected_results: tuple[ScenarioExpectedExpectationExecutionResult, ...] = (),
    assertion_results: tuple[ScenarioAssertionExpectationExecutionResult, ...] = (),
    error_code: str | None = None,
    error_help: str | None = None,
    error_message: str | None = None,
) -> ScenarioRunResult:
    status: ExecutionStatus = (
        ExecutionStatus.FAILED if error_message is not None else ExecutionStatus.SUCCESS
    )
    cleanup_result: ScenarioCleanupExecutionResult | None = None
    if not retain:
        cleanup_result = execute_scenario_cleanup(
            scenario_plan=scenario_plan,
            adapter=adapter,
            connection=connection,
        )
        if cleanup_result.status == ExecutionStatus.FAILED:
            status = ExecutionStatus.FAILED
            if error_code is None:
                error_code = cleanup_result.error_code or SCENARIO_EXEC_CLEANUP_FAILED
                error_help = cleanup_result.error_help
            cleanup_error: str = cleanup_result.error_message or "scenario cleanup failed"
            if error_message is None:
                error_message = f"Cleanup failed: {cleanup_error}"
            else:
                error_message = f"{error_message}\nCleanup failed: {cleanup_error}"
    return ScenarioRunResult(
        scenario_name=scenario_plan.name,
        status=status,
        retained=retain,
        relation_map=scenario_plan.relation_plan.relation_map,
        fixture_results=fixture_results,
        seed_results=seed_results,
        model_results=model_results,
        expected_results=expected_results,
        assertion_results=assertion_results,
        prepare_cleanup_result=prepare_cleanup_result,
        cleanup_result=cleanup_result,
        error_code=error_code,
        error_help=error_help,
        error_message=error_message,
    )


def _scenario_failure(
    *,
    scenario_name: str,
    relation_map: ScenarioRelationMap | None,
    retained: bool,
    error_message: str | None,
    prepare_cleanup_result: ScenarioCleanupExecutionResult | None = None,
    error_code: str | None = None,
    error_help: str | None = None,
) -> ScenarioRunResult:
    return ScenarioRunResult(
        scenario_name=scenario_name,
        status=ExecutionStatus.FAILED,
        retained=retained,
        relation_map=relation_map,
        prepare_cleanup_result=prepare_cleanup_result,
        error_code=error_code,
        error_help=error_help,
        error_message=error_message,
    )


def _has_failed(results: tuple[object, ...]) -> bool:
    return any(getattr(result, "status", None) == ExecutionStatus.FAILED for result in results)


def _first_error(results: tuple[object, ...]) -> str | None:
    result: object
    for result in results:
        if getattr(result, "status", None) == ExecutionStatus.FAILED:
            error_message: object | None = getattr(result, "error_message", None)
            if isinstance(error_message, str) and error_message:
                return error_message
            return "scenario step failed"
    return None


def _first_error_code(results: tuple[object, ...]) -> str | None:
    result: object
    for result in results:
        if getattr(result, "status", None) == ExecutionStatus.FAILED:
            error_code: object | None = getattr(result, "error_code", None)
            if isinstance(error_code, str) and error_code:
                return error_code
    return None


def _first_error_help(results: tuple[object, ...]) -> str | None:
    result: object
    for result in results:
        if getattr(result, "status", None) == ExecutionStatus.FAILED:
            error_help: object | None = getattr(result, "error_help", None)
            if isinstance(error_help, str) and error_help:
                return error_help
    return None
