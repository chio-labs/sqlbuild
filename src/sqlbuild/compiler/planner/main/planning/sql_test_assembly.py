"""Public SQL test planning helpers."""

from __future__ import annotations

from sqlbuild.adapter.classes.base_adapter import BaseAdapter
from sqlbuild.compiler.compile.models.core import CompiledProject
from sqlbuild.compiler.compile.models.sql_tests import CompiledSqlTest
from sqlbuild.compiler.planner._helpers.sql_tests.assembly import plan_test
from sqlbuild.compiler.planner.models import PlanWarning, SqlTestPlanEntry


def build_sql_test_plan_entry(
    *,
    test: CompiledSqlTest,
    project: CompiledProject,
    adapter: BaseAdapter,
    sql_analysis_enabled: bool = False,
) -> tuple[SqlTestPlanEntry, tuple[PlanWarning, ...]]:
    """Build a SQL test plan entry without warehouse state."""

    return plan_test(
        test=test, project=project, adapter=adapter, sql_analysis_enabled=sql_analysis_enabled
    )
