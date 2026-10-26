"""Column facts for custom rules."""

from functools import cached_property

from sqlbuild._native import InferredColumn, Model
from sqlbuild.rule_engine.types import RuleFactModel, RuleFactProject


class ColumnFacts:
    """Declared and compiler-inferred output columns."""

    def __init__(self, *, project: RuleFactProject) -> None:
        self._project: RuleFactProject = project

    @cached_property
    def _models(self) -> dict[object, RuleFactModel]:
        return {model.relative_path: model for model in self._project.models}

    def declared(self, model: Model) -> tuple[object, ...]:
        return self._models[model.path].declared_columns

    def inferred(self, model: Model) -> tuple[InferredColumn, ...] | None:
        return self._models[model.path].inferred_columns

    def enum_types(self, model: Model) -> dict[str, str]:
        return dict(self._models[model.path].enum_type_names)

    def names(self, model: Model) -> tuple[str, ...] | None:
        inferred: tuple[InferredColumn, ...] | None = self.inferred(model)
        return None if inferred is None else tuple(column.name for column in inferred)
