"""Contract facts for custom rules."""

from sqlbuild.compiler.compile.models import CompiledModel, CompiledProject
from sqlbuild.rule_engine.constants import CONTRACT_ENFORCED
from sqlbuild.rule_engine.models import Model


class ContractFacts:
    """Compiler-resolved model contract facts."""

    def __init__(self, *, project: CompiledProject) -> None:
        self._models: dict[object, CompiledModel] = {
            model.relative_path: model for model in project.models
        }

    def enforced(self, model: Model) -> bool:
        value: object = self._models[model.path].config.values.get("contract")
        return value == CONTRACT_ENFORCED

    def grain(self, model: Model) -> tuple[str, ...]:
        value: object = self._models[model.path].config.values.get("grain")
        if isinstance(value, (tuple, list)) and all(isinstance(item, str) for item in value):
            return tuple(str(item) for item in value)
        return ()
