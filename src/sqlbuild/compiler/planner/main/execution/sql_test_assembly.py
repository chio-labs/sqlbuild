"""Public SQL test planning helpers."""

from __future__ import annotations

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.compiler.compile.models import CompiledProject, CompiledSqlTest
from sqlbuild.compiler.planner._helpers.sql_tests.assembly import (
    plan_test,
    resolve_test_model_chain_names,
)
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


def _sql_test_model_chain_names(
    *, test: CompiledSqlTest, project: CompiledProject
) -> tuple[str, ...]:
    """Return the exact model closure a SQL test plan will expand."""

    return resolve_test_model_chain_names(test=test, project=project)
