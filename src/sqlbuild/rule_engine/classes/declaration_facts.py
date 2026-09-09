"""Declaration facts for custom rules."""

from sqlbuild.compiler.compile.models import CompiledProject
from sqlbuild.compiler.discovery.models import ConstantDeclaration, EnumDeclaration


class DeclarationFacts:
    """Compiler-resolved public and model-scoped declarations."""

    def __init__(self, *, project: CompiledProject) -> None:
        self.public_enums: tuple[EnumDeclaration, ...] = tuple(project.public_enums.values())
        self.public_constants: tuple[ConstantDeclaration, ...] = tuple(
            project.public_constants.values()
        )
        enums: list[EnumDeclaration] = list(self.public_enums)
        constants: list[ConstantDeclaration] = list(self.public_constants)
        for model in project.models:
            enums.extend(model.enum_declarations)
            constants.extend(model.constant_declarations)
        self.enums: tuple[EnumDeclaration, ...] = tuple(enums)
        self.constants: tuple[ConstantDeclaration, ...] = tuple(constants)
