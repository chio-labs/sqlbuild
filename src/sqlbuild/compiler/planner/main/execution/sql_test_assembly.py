"""Public SQL test planning helpers."""

from __future__ import annotations

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.compiler.compile.models import CompiledModel, CompiledProject, CompiledSqlTest
from sqlbuild.compiler.planner._helpers.sql_tests.assembly import (
    SqlTestPlanningContext,
    plan_test,
    resolve_test_model_chain_names,
)
from sqlbuild.compiler.planner._helpers.sql_tests.assembly import (
    build_sql_test_planning_context as _build_sql_test_planning_context,
)
from sqlbuild.compiler.planner.models import PlanWarning, SqlTestPlanEntry


def build_sql_test_planning_context(*, project: CompiledProject) -> SqlTestPlanningContext:
    """Build reusable immutable lookup context for static SQL test planning."""

    return _build_sql_test_planning_context(project=project)


def build_sql_test_plan_entry(
    *,
    test: CompiledSqlTest,
    project: CompiledProject,
    adapter: BaseAdapter,
    sql_analysis_enabled: bool = False,
    planning_context: SqlTestPlanningContext | None = None,
) -> tuple[SqlTestPlanEntry, tuple[PlanWarning, ...]]:
    """Build a SQL test plan entry without warehouse state."""

    return plan_test(
        test=test,
        project=project,
        adapter=adapter,
        sql_analysis_enabled=sql_analysis_enabled,
        planning_context=planning_context,
    )


def _sql_test_model_chain_names(
    *,
    test: CompiledSqlTest,
    project: CompiledProject,
    model_map: dict[str, CompiledModel] | None = None,
) -> tuple[str, ...]:
    """Return the exact model closure a SQL test plan will expand."""

    return resolve_test_model_chain_names(test=test, project=project, model_map=model_map)
