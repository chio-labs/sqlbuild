"""Dependency graph facts for custom rules."""

from sqlbuild.compiler.compile.types import CompiledModelView, CompiledProjectView
from sqlbuild.rule_engine.classes.project_tree import public_model
from sqlbuild.rule_engine.models import Model


class GraphFacts:
    """Compiler-resolved model dependencies and dependents."""

    def __init__(self, *, project: CompiledProjectView) -> None:
        self._compiled_by_path: dict[object, CompiledModelView] = {
            model.relative_path: model for model in project.models
        }
        self._by_key: dict[object, Model] = {
            model.key: public_model(model) for model in project.models
        }
        downstream: dict[object, list[Model]] = {}
        for model in project.models:
            for dependency in model.deps:
                downstream.setdefault(dependency, []).append(public_model(model))
        self._downstream: dict[object, list[Model]] = downstream

    def dependencies(self, model: Model) -> tuple[Model, ...]:
        compiled: CompiledModelView = self._compiled_by_path[model.path]
        return tuple(self._by_key[key] for key in compiled.deps if key in self._by_key)

    def dependents(self, model: Model) -> tuple[Model, ...]:
        compiled: CompiledModelView = self._compiled_by_path[model.path]
        return tuple(sorted(self._downstream.get(compiled.key, ()), key=lambda item: item.name))
