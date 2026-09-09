"""Column facts for custom rules."""

from sqlbuild.compiler.compile.models import CompiledModel, CompiledProject, InferredColumn
from sqlbuild.rule_engine.models import Model


class ColumnFacts:
    """Declared and compiler-inferred output columns."""

    def __init__(self, *, project: CompiledProject) -> None:
        self._models: dict[object, CompiledModel] = {
            model.relative_path: model for model in project.models
        }

    def declared(self, model: Model) -> tuple[object, ...]:
        compiled: CompiledModel = self._models[model.path]
        return () if compiled.schema_entry is None else compiled.schema_entry.columns

    def inferred(self, model: Model) -> tuple[InferredColumn, ...] | None:
        return self._models[model.path].inferred_columns

    def names(self, model: Model) -> tuple[str, ...] | None:
        inferred: tuple[InferredColumn, ...] | None = self.inferred(model)
        return None if inferred is None else tuple(column.name for column in inferred)
