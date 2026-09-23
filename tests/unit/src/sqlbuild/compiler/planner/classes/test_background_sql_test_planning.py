from __future__ import annotations

import pytest

import sqlbuild.compiler.planner.classes.background_sql_test_planning as background_module
from sqlbuild.compiler.compile.models import CompiledObjectKey
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.planner.classes.background_sql_test_planning import (
    BackgroundSqlTestPlanning,
)
from sqlbuild.compiler.planner.exceptions import PlannerInputError
from sqlbuild.compiler.planner.models import PlannedSqlTests, PlanWarning
from sqlbuild.compiler.planner.types import WarningSeverity
from tests.unit.src.sqlbuild.compiler.planner.classes._test_types import (
    BackgroundSqlTestPlanningTestCase,
)

_KEYS: frozenset[CompiledObjectKey] = frozenset(
    {CompiledObjectKey(resource_type=CompiledResourceType.MODEL, name="orders")}
)
_PLANNED: PlannedSqlTests = PlannedSqlTests(
    selected_keys=_KEYS,
    warnings=(
        PlanWarning(model_name="orders", severity=WarningSeverity.WARNING, message="planned"),
    ),
)


@pytest.mark.parametrize(
    "test_case",
    [
        BackgroundSqlTestPlanningTestCase(
            description="enabled planning returns the background result",
            enabled=True,
            expected_planner_calls=1,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_enabled_planning_when_joining_then_returns_planned_tests(
    test_case: BackgroundSqlTestPlanningTestCase, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[frozenset[CompiledObjectKey]] = []

    def plan(
        *, project: object, adapter: object, selected_keys: frozenset[CompiledObjectKey]
    ) -> PlannedSqlTests:
        del project, adapter
        calls.append(selected_keys)
        return _PLANNED

    monkeypatch.setattr(background_module, "plan_selected_sql_tests", plan)

    with BackgroundSqlTestPlanning(
        project=object(),  # ty: ignore[invalid-argument-type]
        adapter=object(),  # ty: ignore[invalid-argument-type]
        selected_keys=_KEYS,
        enabled=test_case.enabled,
    ) as planning:
        result: PlannedSqlTests = planning.result()

    assert result == _PLANNED
    assert calls == [_KEYS] * test_case.expected_planner_calls


@pytest.mark.parametrize(
    "test_case",
    [
        BackgroundSqlTestPlanningTestCase(
            description="disabled planning never plans and returns no tests",
            enabled=False,
            expected_planner_calls=0,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_disabled_planning_when_joining_then_returns_empty_tests(
    test_case: BackgroundSqlTestPlanningTestCase, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[frozenset[CompiledObjectKey]] = []

    def plan(
        *, project: object, adapter: object, selected_keys: frozenset[CompiledObjectKey]
    ) -> PlannedSqlTests:
        del project, adapter
        calls.append(selected_keys)
        return _PLANNED

    monkeypatch.setattr(background_module, "plan_selected_sql_tests", plan)

    with BackgroundSqlTestPlanning(
        project=object(),  # ty: ignore[invalid-argument-type]
        adapter=object(),  # ty: ignore[invalid-argument-type]
        selected_keys=_KEYS,
        enabled=test_case.enabled,
    ) as planning:
        result: PlannedSqlTests = planning.result()

    assert result == PlannedSqlTests(selected_keys=_KEYS)
    assert len(calls) == test_case.expected_planner_calls


@pytest.mark.parametrize(
    "test_case",
    [
        BackgroundSqlTestPlanningTestCase(
            description="planning errors surface when joining",
            enabled=True,
            expected_planner_calls=1,
            expected_error="Invalid SQL test fixtures",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_failing_planning_when_joining_then_raises_original_error(
    test_case: BackgroundSqlTestPlanningTestCase, monkeypatch: pytest.MonkeyPatch
) -> None:
    def plan(
        *, project: object, adapter: object, selected_keys: frozenset[CompiledObjectKey]
    ) -> PlannedSqlTests:
        del project, adapter, selected_keys
        raise PlannerInputError(str(test_case.expected_error))

    monkeypatch.setattr(background_module, "plan_selected_sql_tests", plan)

    with BackgroundSqlTestPlanning(
        project=object(),  # ty: ignore[invalid-argument-type]
        adapter=object(),  # ty: ignore[invalid-argument-type]
        selected_keys=_KEYS,
        enabled=test_case.enabled,
    ) as planning:
        with pytest.raises(PlannerInputError, match=str(test_case.expected_error)):
            planning.result()
