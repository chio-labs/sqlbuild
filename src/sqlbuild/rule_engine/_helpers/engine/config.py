"""Resolve rule ignore selectors against the compiled project."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from sqlbuild.compiler.compile.models import CompiledObjectKey
from sqlbuild.compiler.compile.types import CompiledProjectView
from sqlbuild.compiler.planner.main.selection.scope import build_planner_scope
from sqlbuild.compiler.planner.models import PlannerScope
from sqlbuild.rule_engine.exceptions import RulesError
from sqlbuild.rule_engine.models import RuleIgnore, RulesConfig


def resolve_rule_ignore_selectors(
    *, config: RulesConfig, project: CompiledProjectView
) -> RulesConfig:
    """Resolve configured resource selectors into deterministic finding paths."""
    if not any(ignore.selectors for ignore in config.rule_ignores):
        return config
    path_by_key: dict[CompiledObjectKey, Path] = _resource_paths(project=project)
    resolved: list[RuleIgnore] = []
    for ignore in config.rule_ignores:
        if not ignore.selectors:
            resolved.append(ignore)
            continue
        scope: PlannerScope = build_planner_scope(project=project, select=ignore.selectors)
        selector_paths: set[str] = {
            path_by_key[key].as_posix() for key in scope.selected_keys if key in path_by_key
        }
        if not selector_paths:
            joined: str = ", ".join(ignore.selectors)
            raise RulesError(f"rule ignore selectors resolve no resources with paths: {joined}")
        resolved.append(
            replace(
                ignore,
                paths=tuple(sorted({*ignore.paths, *selector_paths})),
                selectors=(),
            )
        )
    return replace(config, rule_ignores=tuple(resolved))


def _resource_paths(*, project: CompiledProjectView) -> dict[CompiledObjectKey, Path]:
    paths: dict[CompiledObjectKey, Path] = {
        model.key: model.relative_path for model in project.models
    }
    paths.update({function.key: function.relative_path for function in project.functions})
    paths.update({seed.key: seed.seed_file.relative_path for seed in project.seeds})
    paths.update({source.key: source.source_file.relative_path for source in project.sources})
    return paths
