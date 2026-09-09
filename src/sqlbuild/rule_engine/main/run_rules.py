"""Unified compiler-rule orchestration entrypoint."""

from pathlib import Path

from sqlbuild.compiler.compile.models import CompiledObjectKey
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.compiler.pipeline.models import ProjectGraph
from sqlbuild.rule_engine._helpers.run.rules import evaluate_rules
from sqlbuild.rule_engine.models import RulesConfig, RulesRunResult


def run_rules(
    *,
    graph: ProjectGraph,
    discovered_inputs: DiscoveredProjectInputs,
    config: RulesConfig,
    project_dir: Path,
    dialect: str,
    selected_keys: frozenset[CompiledObjectKey] | None = None,
) -> RulesRunResult:
    """Run selected native built-ins before selected custom Python rules."""

    return evaluate_rules(
        graph=graph,
        discovered_inputs=discovered_inputs,
        config=config,
        project_dir=project_dir,
        dialect=dialect,
        selected_keys=selected_keys,
    )
