"""Whole-project facts for custom rules."""

from pathlib import Path

from sqlbuild._native import (
    Model,
    compiled_audit_record,
    compiled_function_record,
    compiled_seed_record,
    compiled_source_record,
)
from sqlbuild.compiler.compile.types import CompiledProjectView
from sqlbuild.rule_engine.classes.project_tree import ProjectTree, public_model


class ProjectFacts:
    """Compiler-owned project resources and deterministic project tree."""

    def __init__(self, *, project: CompiledProjectView, project_dir: Path) -> None:
        self.models: tuple[Model, ...] = tuple(
            public_model(model)
            for model in sorted(project.models, key=lambda item: item.relative_path.as_posix())
        )
        self.sources: tuple[object, ...] = tuple(map(compiled_source_record, project.sources))
        self.seeds: tuple[object, ...] = tuple(map(compiled_seed_record, project.seeds))
        self.functions: tuple[object, ...] = tuple(map(compiled_function_record, project.functions))
        self.tests: tuple[object, ...] = project.sql_tests
        self.audits: tuple[object, ...] = tuple(map(compiled_audit_record, project.audits))
        self.tree: ProjectTree = ProjectTree(
            project_dir=project_dir, project=project, models=self.models
        )
