"""Focused compiler-rule command implementation."""

from __future__ import annotations

import json
import sys
from dataclasses import replace
from pathlib import Path

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.cli.commands._helpers.runtime.adapters import resolve_adapter
from sqlbuild.cli.commands.constants import (
    RULES_LIST_ACTION,
    RULES_SHOW_ACTION,
    RULES_SKILLS_ACTION,
)
from sqlbuild.cli.commands.models import RulesCommandRequest
from sqlbuild.compiler.compile.models import CompiledObjectKey
from sqlbuild.compiler.discovery.main.discover import discover_project_inputs
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.compiler.pipeline.main.graph import build_project_graph
from sqlbuild.compiler.pipeline.models import ProjectGraph
from sqlbuild.compiler.planner.main.selection.selection import resolve_project_selectors
from sqlbuild.rule_engine.main.build_catalogue import build_catalogue
from sqlbuild.rule_engine.main.load_config import load_rules_config
from sqlbuild.rule_engine.main.render_result import format_result
from sqlbuild.rule_engine.main.render_rule import format_rule
from sqlbuild.rule_engine.main.run_rules import run_rules
from sqlbuild.rule_engine.main.skills import install_skills
from sqlbuild.rule_engine.models import Rule, RulesConfig, RulesResult, RulesRunResult
from sqlbuild.spec.contracts.main.resolve_effective_adapter_name import (
    resolve_effective_adapter_name,
)


def run_rules_command(request: RulesCommandRequest) -> int:
    """List, inspect, execute, or generate guidance for compiler rules."""

    project_dir: Path = (
        Path.cwd() if request.project_dir is None else request.project_dir
    ).resolve()
    config: RulesConfig = load_rules_config(project_dir=project_dir)
    if request.action == RULES_SKILLS_ACTION:
        return _run_skills(request=request, config=config, project_dir=project_dir)
    catalogue: tuple[Rule, ...] = build_catalogue(config=config, project_dir=project_dir)
    if request.action == RULES_LIST_ACTION:
        return _list_rules(catalogue=catalogue, json_output=request.json_output)
    return _run_catalogue_action(
        request=request,
        catalogue=catalogue,
        config=config,
        project_dir=project_dir,
    )


def _run_skills(*, request: RulesCommandRequest, config: RulesConfig, project_dir: Path) -> int:
    fresh: bool = install_skills(config=config, project_dir=project_dir, check=request.skills_check)
    if request.skills_check:
        print("Rules skills are fresh" if fresh else "Rules skills are stale")
        return 0 if fresh else 1
    print("Installed Rules skills")
    return 0


def _list_rules(*, catalogue: tuple[Rule, ...], json_output: bool) -> int:
    if json_output:
        payload: dict[str, object] = {
            "rules": [
                {
                    "code": rule.code,
                    "family": rule.family,
                    "message": rule.message,
                    "custom": rule.custom,
                    "subject": rule.subject.value if rule.subject is not None else None,
                }
                for rule in catalogue
            ]
        }
        print(json.dumps(payload, sort_keys=True))
    else:
        print("\n".join(f"{rule.code}  {rule.message}" for rule in catalogue))
    return 0


def _run_catalogue_action(
    *,
    request: RulesCommandRequest,
    catalogue: tuple[Rule, ...],
    config: RulesConfig,
    project_dir: Path,
) -> int:
    selector: str | None = request.rule_selector
    if selector is None:
        print("A rule code or family prefix is required")
        return 2
    if request.action == RULES_SHOW_ACTION:
        return _show_rule(selector=selector, catalogue=catalogue, config=config)
    return _run_rule_selection(
        request=request,
        selector=selector,
        catalogue=catalogue,
        config=config,
        project_dir=project_dir,
    )


def _show_rule(*, selector: str, catalogue: tuple[Rule, ...], config: RulesConfig) -> int:
    matching: tuple[Rule, ...] = tuple(rule for rule in catalogue if rule.code == selector)
    if not matching:
        print(f"Unknown rule: {selector}")
        return 2
    print(format_rule(rule=matching[0], config=config))
    return 0


def _run_rule_selection(
    *,
    request: RulesCommandRequest,
    selector: str,
    catalogue: tuple[Rule, ...],
    config: RulesConfig,
    project_dir: Path,
) -> int:
    if not any(rule.code.startswith(selector) for rule in catalogue):
        print(f"Unknown rule or family: {selector}")
        return 2
    print(f"Evaluating rule selection {selector}...", file=sys.stderr)
    discovered: DiscoveredProjectInputs = discover_project_inputs(project_dir=project_dir)
    adapter: BaseAdapter = resolve_adapter(
        adapter_name=resolve_effective_adapter_name(
            project_config=discovered.project_config,
            local_config=discovered.local_config,
        ),
        project_dir=project_dir,
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
    result: RulesRunResult = run_rules(
        graph=graph,
        discovered_inputs=discovered,
        config=replace(config, select=(selector,), ignore=()),
        project_dir=project_dir,
        dialect=adapter.sql_analysis_dialect() or "generic",
        selected_keys=selected_keys if request.select or request.exclude else None,
    )
    print(
        format_result(
            result=RulesResult(
                findings=result.findings,
                evaluated_models=result.evaluated_models,
                cache_hits=result.cache_hits,
                cache_misses=result.cache_misses,
            ),
            json_output=request.json_output,
        )
    )
    if result.findings:
        print(
            f"Rule selection {selector} failed with {len(result.findings)} finding(s).",
            file=sys.stderr,
        )
        return 1
    print(f"Rule selection {selector} passed.", file=sys.stderr)
    return 0
