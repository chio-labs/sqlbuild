"""Policy project evaluation entrypoint."""

from pathlib import Path

from sqlbuild.compiler.compile.models import CompiledProject
from sqlbuild.policy_engine._helpers.engine.ruleset import evaluate_project
from sqlbuild.policy_engine.models import PolicyConfig, PolicyResult


def evaluate(
    *,
    project: CompiledProject,
    config: PolicyConfig,
    project_dir: Path,
    dialect: str = "generic",
) -> PolicyResult:
    """Evaluate the selected project policy over compiled models."""

    return evaluate_project(
        project=project,
        config=config,
        project_dir=project_dir,
        dialect=dialect,
    )
