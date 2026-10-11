"""Column facts for custom rules."""

from functools import cached_property

from sqlbuild.compiler.compile.models import InferredColumn
from sqlbuild.compiler.compile.types import CompiledModelView, CompiledProjectView
from sqlbuild.rule_engine.models import Model


class ColumnFacts:
    """Declared and compiler-inferred output columns."""

    def __init__(self, *, project: CompiledProjectView) -> None:
        self._project: CompiledProjectView = project

    @cached_property
    def _models(self) -> dict[object, CompiledModelView]:
        return {model.relative_path: model for model in self._project.models}

    def declared(self, model: Model) -> tuple[object, ...]:
        compiled: CompiledModelView = self._models[model.path]
        return () if compiled.schema_entry is None else compiled.schema_entry.columns

    def inferred(self, model: Model) -> tuple[InferredColumn, ...] | None:
        return self._models[model.path].inferred_columns

    def names(self, model: Model) -> tuple[str, ...] | None:
        inferred: tuple[InferredColumn, ...] | None = self.inferred(model)
        return None if inferred is None else tuple(column.name for column in inferred)
