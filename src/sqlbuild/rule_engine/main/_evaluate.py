"""Rules project evaluation entrypoint used by the public test harness."""

from pathlib import Path

from sqlbuild._native import (
    build_rule_catalogue,
    resolve_rule_ignore_selectors,
    select_catalogue_rules,
)
from sqlbuild.compiler.compile.types import CompiledProjectView
from sqlbuild.rule_engine._helpers.engine.custom_dispatch import evaluate_native
from sqlbuild.rule_engine._helpers.engine.hermeticity import verify_custom_rules
from sqlbuild.rule_engine.models import Rule, RulesConfig, RulesResult


def evaluate(
    *,
    project: CompiledProjectView,
    config: RulesConfig,
    project_dir: Path,
    dialect: str = "generic",
    verify_determinism: bool = False,
) -> RulesResult:
    """Evaluate the selected compiler rules over compiled models."""

    effective_config: RulesConfig = resolve_rule_ignore_selectors(config=config, project=project)
    catalogue: tuple[Rule, ...] = build_rule_catalogue(
        config=effective_config, project_dir=project_dir
    )
    if any(rule.custom for rule in catalogue):
        _ = verify_custom_rules(
            rules=select_catalogue_rules(
                catalogue=catalogue, config=effective_config, project_dir=project_dir
            ),
            project_dir=project_dir,
        )
    return evaluate_native(
        project=project,
        config=effective_config,
        project_dir=project_dir,
        catalogue=catalogue,
        dialect=dialect,
        verify_determinism=verify_determinism,
    )
