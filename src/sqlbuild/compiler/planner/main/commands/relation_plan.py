"""Public relation-only plan entrypoint."""

from sqlbuild.compiler.compile.types import CompiledProjectView
from sqlbuild.compiler.planner._helpers.command_planning.static import (
    build_relation_command_plan_impl,
)
from sqlbuild.compiler.planner.models import PlannerRelationsContext, PlannerScope, PlanOutput


def build_relation_command_plan(
    *, project: CompiledProjectView, scope: PlannerScope, relations: PlannerRelationsContext
) -> PlanOutput:
    """Project static relation data for Python checks."""

    return build_relation_command_plan_impl(project=project, scope=scope, relations=relations)
