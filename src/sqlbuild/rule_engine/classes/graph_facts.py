"""Dependency graph facts for custom rules."""

from functools import cached_property

from sqlbuild.compiler.compile.types import CompiledModelView, CompiledProjectView
from sqlbuild.rule_engine.classes.project_tree import public_model
from sqlbuild.rule_engine.models import Model


class GraphFacts:
    """Compiler-resolved model dependencies and dependents."""

    def __init__(
        self, *, project: CompiledProjectView, models: tuple[Model, ...] | None = None
    ) -> None:
        self._project: CompiledProjectView = project
        self._models: tuple[Model, ...] | None = models

    @cached_property
    def _compiled_by_path(self) -> dict[object, CompiledModelView]:
        return {model.relative_path: model for model in self._project.models}

    @cached_property
    def _by_key(self) -> dict[object, Model]:
        model_views: tuple[Model, ...] = (
            tuple(public_model(item) for item in self._project.models)
            if self._models is None
            else self._models
        )
        public_by_path: dict[object, Model] = {item.path: item for item in model_views}
        return {model.key: public_by_path[model.relative_path] for model in self._project.models}

    @cached_property
    def _downstream(self) -> dict[object, list[Model]]:
        downstream: dict[object, list[Model]] = {}
        for model in self._project.models:
            subject: Model = self._by_key[model.key]
            for dependency in model.deps:
                downstream.setdefault(dependency, []).append(subject)
        return downstream

    def dependencies(self, model: Model) -> tuple[Model, ...]:
        compiled: CompiledModelView = self._compiled_by_path[model.path]
        return tuple(self._by_key[key] for key in compiled.deps if key in self._by_key)

    def dependents(self, model: Model) -> tuple[Model, ...]:
        compiled: CompiledModelView = self._compiled_by_path[model.path]
        return tuple(sorted(self._downstream.get(compiled.key, ()), key=lambda item: item.name))
