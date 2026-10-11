"""Rules project evaluation entrypoint used by the public test harness."""

from pathlib import Path

from sqlbuild.compiler.compile.types import CompiledProjectView
from sqlbuild.rule_engine._helpers.engine.ruleset import evaluate_project
from sqlbuild.rule_engine.models import RulesConfig, RulesResult


def evaluate(
    *,
    project: CompiledProjectView,
    config: RulesConfig,
    project_dir: Path,
    dialect: str = "generic",
    verify_determinism: bool = False,
) -> RulesResult:
    """Evaluate the selected compiler rules over compiled models."""

    return evaluate_project(
        project=project,
        config=config,
        project_dir=project_dir,
        dialect=dialect,
        verify_determinism=verify_determinism,
    )
