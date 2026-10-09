"""Plan and render SQL test artifacts natively for the preview compiler engine."""

from __future__ import annotations

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.compiler.compile.models import CompiledProject, CompiledSqlTest
from sqlbuild.compiler.planner.main.execution._plan_compiled_sql_test_artifacts import (
    plan_compiled_sql_test_artifacts,
)
from sqlbuild.compiler.planner.models import NativeSqlTestArtifact


def plan_native_sql_test_artifacts(
    *,
    project: CompiledProject,
    tests: tuple[CompiledSqlTest, ...],
    adapter: BaseAdapter,
    sql_analysis_enabled: bool,
) -> tuple[NativeSqlTestArtifact, ...]:
    """Return one artifact per test, planned from the compiled objects without a JSON request."""

    return plan_compiled_sql_test_artifacts(
        project=project,
        tests=tests,
        adapter=adapter,
        sql_analysis_enabled=sql_analysis_enabled,
    )
