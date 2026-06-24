"""Standard reuse option resolution helpers."""

from __future__ import annotations

from sqlbuild.compiler.compile.models.core import CompiledObjectKey, CompiledProject
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.planner.models import PlannerChangeResults, PlannerScope
from sqlbuild.compiler.planner.types import ChangeKind
from sqlbuild.spec.models.project import LocalConfig, ProjectConfig, TargetConfig
from sqlbuild.spec.models.targets import resolve_target_config


def build_current_project_affected_model_names(
    *, scope: PlannerScope, changes: PlannerChangeResults
) -> frozenset[str]:
    changed_model_names: frozenset[str] = frozenset(
        model_name
        for model_name, change in changes.models.items()
        if change.change_kind
        in {
            ChangeKind.QUERY_CHANGED,
            ChangeKind.CONFIG_CHANGED,
            ChangeKind.SCHEMA_CHANGED,
        }
    )
    root_keys: set[CompiledObjectKey] = {
        key
        for name in changed_model_names
        if (key := scope.all_keys.get(name)) is not None
        and key.resource_type == CompiledResourceType.MODEL
    }
    affected: set[str] = set(changed_model_names)
    stack: list[CompiledObjectKey] = list(root_keys)
    seen: set[CompiledObjectKey] = set(root_keys)
    while stack:
        key: CompiledObjectKey = stack.pop()
        for downstream_key in scope.downstream_deps.get(key, ()):
            if downstream_key in seen:
                continue
            seen.add(downstream_key)
            if downstream_key.resource_type == CompiledResourceType.MODEL:
                affected.add(downstream_key.name)
                stack.append(downstream_key)
    return frozenset(affected)


def resolve_standard_reuse_strict(
    *,
    project: CompiledProject,
    project_config: ProjectConfig | None,
    local_config: LocalConfig | None,
    override: bool | None,
) -> bool:
    if override is not None:
        return override
    target_config: TargetConfig | None = _standard_target_config(
        project=project, project_config=project_config, local_config=local_config
    )
    return target_config.reuse_strict if target_config is not None else False


def resolve_standard_trust_reuse_inputs(
    *,
    project: CompiledProject,
    project_config: ProjectConfig | None,
    local_config: LocalConfig | None,
    override: bool | None,
) -> bool:
    if override is not None:
        return override
    target_config: TargetConfig | None = _standard_target_config(
        project=project, project_config=project_config, local_config=local_config
    )
    return target_config.trust_reuse_inputs if target_config is not None else False


def _standard_target_config(
    *,
    project: CompiledProject,
    project_config: ProjectConfig | None,
    local_config: LocalConfig | None,
) -> TargetConfig | None:
    if project_config is None or local_config is None or project.effective_target_name is None:
        return None
    return resolve_target_config(
        project_config=project_config,
        local_config=local_config,
        target_name=project.effective_target_name,
    )
