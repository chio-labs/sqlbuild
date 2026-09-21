"""SQL test planning context entrypoint."""

from sqlbuild.compiler.compile.models import CompiledProject
from sqlbuild.compiler.planner._helpers.sql_tests.assembly import (
    SqlTestPlanningContext,
)
from sqlbuild.compiler.planner._helpers.sql_tests.assembly import (
    build_sql_test_planning_context as _build_sql_test_planning_context,
)


def build_sql_test_planning_context(*, project: CompiledProject) -> SqlTestPlanningContext:
    """Build reusable immutable lookup context for static SQL test planning."""

    return _build_sql_test_planning_context(project=project)
