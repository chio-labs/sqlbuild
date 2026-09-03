"""Public focused seed-plan entrypoint."""

from sqlbuild.compiler.compile.models import CompiledProject
from sqlbuild.compiler.fingerprints.models import Fingerprint
from sqlbuild.compiler.planner._helpers.command_planning.static import build_seed_command_plan_impl
from sqlbuild.compiler.planner.models import PlannerRelationsContext, PlannerScope, PlanOutput


def build_seed_command_plan(
    *,
    project: CompiledProject,
    scope: PlannerScope,
    relations: PlannerRelationsContext,
    fingerprints: dict[str, Fingerprint] | None = None,
) -> PlanOutput:
    """Project selected direct seed work and canonical identities."""

    return build_seed_command_plan_impl(
        project=project, scope=scope, relations=relations, fingerprints=fingerprints
    )
