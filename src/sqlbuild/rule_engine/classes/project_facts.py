"""Whole-project facts for custom rules."""

from pathlib import Path

from sqlbuild.compiler.compile.models import CompiledProject
from sqlbuild.rule_engine.classes.project_tree import ProjectTree, public_model
from sqlbuild.rule_engine.models import Model


class ProjectFacts:
    """Compiler-owned project resources and deterministic project tree."""

    def __init__(self, *, project: CompiledProject, project_dir: Path) -> None:
        self.models: tuple[Model, ...] = tuple(
            public_model(model)
            for model in sorted(project.models, key=lambda item: item.relative_path.as_posix())
        )
        self.sources: tuple[object, ...] = project.sources
        self.seeds: tuple[object, ...] = project.seeds
        self.functions: tuple[object, ...] = project.functions
        self.tests: tuple[object, ...] = project.sql_tests
        self.audits: tuple[object, ...] = project.audits
        self.tree: ProjectTree = ProjectTree(project_dir=project_dir, project=project)
