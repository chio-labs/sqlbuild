"""Public focused audit-plan entrypoint."""

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.compiler.compile.types import CompiledProjectView
from sqlbuild.compiler.planner._helpers.command_planning.static import build_audit_command_plan_impl
from sqlbuild.compiler.planner.models import PlannerRelationsContext, PlannerScope, PlanOutput


def build_audit_command_plan(
    *,
    project: CompiledProjectView,
    adapter: BaseAdapter,
    scope: PlannerScope,
    relations: PlannerRelationsContext,
) -> PlanOutput:
    """Project selected audits from canonical static state."""

    return build_audit_command_plan_impl(
        project=project, adapter=adapter, scope=scope, relations=relations
    )
