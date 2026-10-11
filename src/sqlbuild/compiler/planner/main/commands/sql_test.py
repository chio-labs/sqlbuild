"""Public focused SQL-test plan entrypoint."""

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.compiler.compile.types import CompiledProjectView
from sqlbuild.compiler.planner._helpers.command_planning.static import build_test_command_plan_impl
from sqlbuild.compiler.planner.models import PlannerRelationsContext, PlannerScope, PlanOutput


def build_test_command_plan(
    *,
    project: CompiledProjectView,
    adapter: BaseAdapter,
    scope: PlannerScope,
    relations: PlannerRelationsContext,
    case_name: str | None = None,
) -> PlanOutput:
    """Project selected SQL tests from canonical static state."""

    return build_test_command_plan_impl(
        project=project,
        adapter=adapter,
        scope=scope,
        relations=relations,
        case_name=case_name,
    )
