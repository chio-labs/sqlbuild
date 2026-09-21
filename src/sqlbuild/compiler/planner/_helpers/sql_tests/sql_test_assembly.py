"""Public SQL test planning helpers."""

from __future__ import annotations

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.compiler.compile.models import CompiledProject, CompiledSqlTest
from sqlbuild.compiler.planner._helpers.sql_tests.assembly import (
    SqlTestPlanningContext,
    plan_test,
)
from sqlbuild.compiler.planner.models import PlanWarning, SqlTestPlanEntry


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
