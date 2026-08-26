"""CLI kata command entrypoints."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.cli.commands._helpers.runtime.adapters import resolve_adapter
from sqlbuild.cli.commands.models import KataCommandRequest
from sqlbuild.compiler.compile.models import CompiledObjectKey, CompiledProject
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.discovery.main.discover import discover_project_inputs
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.compiler.pipeline.main.graph import build_project_graph
from sqlbuild.compiler.pipeline.models import ProjectGraph
from sqlbuild.compiler.planner.main.selection.selection import resolve_project_selectors
from sqlbuild.kata_engine.main.build_catalogue import build_catalogue
from sqlbuild.kata_engine.main.evaluate import evaluate
from sqlbuild.kata_engine.main.load_config import load_kata_config
from sqlbuild.kata_engine.main.render_result import format_result
from sqlbuild.kata_engine.main.render_rule import format_rule
from sqlbuild.kata_engine.main.skills import install_skills
from sqlbuild.kata_engine.models import KataConfig, KataResult, KataRule
from sqlbuild.spec.contracts.main.resolve_effective_adapter_name import (
    resolve_effective_adapter_name,
)


def run_kata_command(
    request: KataCommandRequest,
) -> int:
    """Inspect one rule or evaluate the selected kata policy."""

    base_dir: Path = (Path.cwd() if request.project_dir is None else request.project_dir).resolve()
    config: KataConfig = load_kata_config(project_dir=base_dir)
    if request.skills:
        fresh: bool = install_skills(
            config=config, project_dir=base_dir, check=request.skills_check
        )
        if request.skills_check:
            print("Kata skills are fresh" if fresh else "Kata skills are stale")
            return 0 if fresh else 1
        print("Installed kata skills")
        return 0
    if request.rule_code is not None:
        rules: tuple[KataRule, ...] = build_catalogue(config=config, project_dir=base_dir)
        matching: tuple[KataRule, ...] = tuple(
            rule for rule in rules if rule.code == request.rule_code
        )
        if not matching:
            print(f"Unknown kata rule: {request.rule_code}")
            return 2
        print(format_rule(rule=matching[0], config=config))
        return 0
    discovered: DiscoveredProjectInputs = discover_project_inputs(project_dir=base_dir)
    adapter: BaseAdapter = resolve_adapter(
        adapter_name=resolve_effective_adapter_name(
            project_config=discovered.project_config,
            local_config=discovered.local_config,
        ),
        project_dir=base_dir,
    )
    graph: ProjectGraph = build_project_graph(discovered_inputs=discovered, adapter=adapter)
    selected_keys: frozenset[CompiledObjectKey] = resolve_project_selectors(
        select=request.select,
        exclude=request.exclude,
        all_keys=graph.all_keys,
        upstream_deps=graph.upstream_deps,
        downstream_deps=graph.downstream_deps,
        tag_index=graph.tag_index,
        path_index=graph.path_index,
    )
    selected_names: frozenset[str] = frozenset(
        key.name for key in selected_keys if key.resource_type == CompiledResourceType.MODEL
    )
    project: CompiledProject = replace(
        graph.project,
        models=tuple(model for model in graph.project.models if model.name in selected_names),
    )
    result: KataResult = evaluate(project=project, config=config, project_dir=base_dir)
    print(format_result(result=result, json_output=request.json_output))
    return 1 if result.faults else 0
