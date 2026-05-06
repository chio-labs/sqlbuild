"""Public SQL test planning helpers."""

from __future__ import annotations

from sqlbuild.compiler.compile.models import CompiledProject, CompiledSqlTest
from sqlbuild.compiler.planner.helpers.sql_test_assembly import plan_test
from sqlbuild.compiler.planner.models import PlanWarning, SqlTestPlanEntry


def build_sql_test_plan_entry(
    *,
    test: CompiledSqlTest,
    project: CompiledProject,
    sqlglot_enabled: bool = False,
) -> tuple[SqlTestPlanEntry, tuple[PlanWarning, ...]]:
    """Build a SQL test plan entry without warehouse state."""

    return plan_test(test=test, project=project, sqlglot_enabled=sqlglot_enabled)
