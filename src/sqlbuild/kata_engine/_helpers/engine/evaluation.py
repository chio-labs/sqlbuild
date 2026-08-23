"""Kata project evaluation orchestration."""

from __future__ import annotations

from pathlib import Path

from sqlbuild.compiler.compile.models import CompiledProject
from sqlbuild.kata_engine._helpers.engine.catalogue import build_catalogue, select_rules
from sqlbuild.kata_engine._helpers.engine.hermeticity import verify_custom_rules
from sqlbuild.kata_engine._helpers.engine.native import evaluate_native
from sqlbuild.kata_engine.models import KataConfig, KataResult, KataRule


def evaluate_project(
    *, project: CompiledProject, config: KataConfig, project_dir: Path
) -> KataResult:
    """Evaluate selected rules through one native project boundary."""

    catalogue: tuple[KataRule, ...] = build_catalogue(config=config, project_dir=project_dir)
    if config.cache.require_cacheable and any(rule.custom for rule in catalogue):
        selected: tuple[KataRule, ...] = select_rules(catalogue=catalogue, config=config)
        verify_custom_rules(rules=selected, project_dir=project_dir)
    return evaluate_native(
        project=project,
        config=config,
        project_dir=project_dir,
        catalogue=catalogue,
    )
