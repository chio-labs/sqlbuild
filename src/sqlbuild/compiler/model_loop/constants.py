"""Codes the native model loop shares with its Rust bindings."""

from sqlbuild.compiler.scopes.types import DeclarationKind

DECLARATION_KIND_CODES: dict[DeclarationKind, int] = {
    DeclarationKind.ENUM: 0,
    DeclarationKind.CONSTANT: 1,
    DeclarationKind.MACRO: 2,
}
NO_DECLARATION_KIND: int = 255
