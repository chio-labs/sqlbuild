"""Whole-project facts for custom rules."""

from functools import cached_property
from pathlib import Path

from sqlbuild._native import (
    Model,
    compiled_audit_record,
    compiled_function_record,
    compiled_seed_record,
    compiled_source_record,
)
from sqlbuild.rule_engine.classes.project_tree import ProjectTree, public_model
from sqlbuild.rule_engine.types import RuleFactProject


class ProjectFacts:
    """Compiler-owned project resources and deterministic project tree."""

    def __init__(self, *, project: RuleFactProject, project_dir: Path) -> None:
        self._project: RuleFactProject = project
        self.models: tuple[Model, ...] = tuple(
            public_model(model)
            for model in sorted(project.models, key=lambda item: item.relative_path.as_posix())
        )
        self.tree: ProjectTree = ProjectTree(
            project_dir=project_dir, project=project, models=self.models
        )

    @cached_property
    def sources(self) -> tuple[object, ...]:
        return tuple(map(compiled_source_record, self._project.sources))

    @cached_property
    def seeds(self) -> tuple[object, ...]:
        return tuple(map(compiled_seed_record, self._project.seeds))

    @cached_property
    def functions(self) -> tuple[object, ...]:
        return tuple(map(compiled_function_record, self._project.functions))

    @cached_property
    def tests(self) -> tuple[object, ...]:
        return self._project.sql_tests

    @cached_property
    def audits(self) -> tuple[object, ...]:
        return tuple(map(compiled_audit_record, self._project.audits))
