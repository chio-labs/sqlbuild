"""Declaration facts for custom rules."""

from functools import cached_property

from sqlbuild._native import ConstantDeclaration, EnumDeclaration
from sqlbuild.rule_engine.types import RuleFactProject


class DeclarationFacts:
    """Compiler-resolved public and model-scoped declarations."""

    def __init__(self, *, project: RuleFactProject) -> None:
        self._project: RuleFactProject = project

    @cached_property
    def public_enums(self) -> tuple[EnumDeclaration, ...]:
        return tuple(self._project.public_enums.values())

    @cached_property
    def public_constants(self) -> tuple[ConstantDeclaration, ...]:
        return tuple(self._project.public_constants.values())

    @cached_property
    def enums(self) -> tuple[EnumDeclaration, ...]:
        enums: list[EnumDeclaration] = list(self.public_enums)
        for model in self._project.models:
            enums.extend(model.enum_declarations)
        return tuple(enums)

    @cached_property
    def constants(self) -> tuple[ConstantDeclaration, ...]:
        constants: list[ConstantDeclaration] = list(self.public_constants)
        for model in self._project.models:
            constants.extend(model.constant_declarations)
        return tuple(constants)
