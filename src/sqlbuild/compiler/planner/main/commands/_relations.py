"""Focused-command relation entrypoint."""

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.compiler.compile.models import CompiledObjectKey, CompiledProject
from sqlbuild.compiler.planner._helpers.command_planning.static import (
    resolve_static_relation_context_impl,
)
from sqlbuild.compiler.planner.models import DeferralInputs, PlannerRelationsContext, PlannerScope
from sqlbuild.spec.contracts.models import LocalConfig, ProjectConfig


def resolve_static_relation_context(
    *,
    project: CompiledProject,
    adapter: BaseAdapter,
    scope: PlannerScope,
    deferral: DeferralInputs | None = None,
    project_config: ProjectConfig | None = None,
    local_config: LocalConfig | None = None,
    relation_keys: frozenset[CompiledObjectKey] | None = None,
) -> PlannerRelationsContext:
    """Resolve canonical locations and source routing without warehouse inventory."""

    return resolve_static_relation_context_impl(
        project=project,
        adapter=adapter,
        scope=scope,
        deferral=deferral,
        project_config=project_config,
        local_config=local_config,
        relation_keys=relation_keys,
    )
