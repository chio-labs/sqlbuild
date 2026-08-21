"""Kata project evaluation entrypoint."""

from pathlib import Path

from sqlbuild.compiler.compile.models import CompiledProject
from sqlbuild.kata_engine._helpers.engine.evaluation import evaluate_project
from sqlbuild.kata_engine.models import KataConfig, KataResult


def evaluate(*, project: CompiledProject, config: KataConfig, project_dir: Path) -> KataResult:
    """Evaluate the selected kata policy over compiled models."""

    return evaluate_project(project=project, config=config, project_dir=project_dir)
