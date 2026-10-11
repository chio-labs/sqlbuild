"""Declaration rows native consumers read."""

from sqlbuild.compiler.compiled_project._helpers.rows import constant_row, enum_row
from sqlbuild.compiler.discovery.models import ConstantDeclaration, EnumDeclaration


def declaration_rows(
    *, enums: tuple[EnumDeclaration, ...], constants: tuple[ConstantDeclaration, ...]
) -> tuple[list[tuple[object, ...]], list[tuple[object, ...]]]:
    """Return enum and constant declarations as native rows, in the given order."""

    return [enum_row(declaration) for declaration in enums], [
        constant_row(declaration) for declaration in constants
    ]
