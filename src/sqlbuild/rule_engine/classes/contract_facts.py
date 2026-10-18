"""Contract facts for custom rules."""

from sqlbuild._native import CONTRACT_ENFORCED, Model
from sqlbuild.rule_engine.types import RuleFactModel, RuleFactProject


class ContractFacts:
    """Compiler-resolved model contract facts."""

    def __init__(self, *, project: RuleFactProject) -> None:
        self._models: dict[object, RuleFactModel] = {
            model.relative_path: model for model in project.models
        }

    def enforced(self, model: Model) -> bool:
        value: object = self._models[model.path].config_value("contract")
        return value == CONTRACT_ENFORCED

    def grain(self, model: Model) -> tuple[str, ...]:
        value: object = self._models[model.path].config_value("grain")
        if isinstance(value, (tuple, list)) and all(isinstance(item, str) for item in value):
            return tuple(str(item) for item in value)
        return ()
