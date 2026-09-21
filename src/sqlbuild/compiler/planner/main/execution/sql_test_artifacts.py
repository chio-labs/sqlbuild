"""Public planner entrypoint for compiled SQL-test artifacts."""

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.compiler.compile.models import CompiledProject, CompiledSqlTest
from sqlbuild.compiler.planner._helpers.sql_tests.native_planning import (
    plan_and_render_sql_test_artifacts as _plan_and_render_sql_test_artifacts,
)
from sqlbuild.compiler.planner.models import NativeSqlTestArtifact


def plan_and_render_sql_test_artifacts(
    *,
    project: CompiledProject,
    tests: tuple[CompiledSqlTest, ...],
    adapter: BaseAdapter,
    sql_analysis_enabled: bool,
) -> tuple[NativeSqlTestArtifact, ...]:
    """Plan and render SQL tests in one deterministic native project call."""

    return _plan_and_render_sql_test_artifacts(
        project=project,
        tests=tests,
        adapter=adapter,
        sql_analysis_enabled=sql_analysis_enabled,
    )
